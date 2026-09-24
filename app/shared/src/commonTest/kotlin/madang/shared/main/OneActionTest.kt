package madang.shared.main

import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.Project
import madang.api.model.RunRecord
import madang.api.model.RunResultStatus
import madang.api.model.RunTrigger
import madang.api.model.RunUsage
import madang.api.model.RunVerify
import madang.api.model.Target
import madang.shared.LocalFiles
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventTransport
import madang.shared.json
import madang.shared.settings.AppSettings
import madang.shared.settings.InMemorySettingsStore

/**
 * 한 동작: 보내기 뒤 결과 블록(머지·게시 상태, 되돌리기, 다시 실행)과 묻는 블록의 답이 모두 core
 * API 한 경로로 가는지, 읽지 않음이 앱 설정에 남는지 본다.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OneActionTest {

    private val codec = CoreClient.CoreJson
    private val events = Channel<String>(Channel.UNLIMITED)
    private val routes =
        mutableMapOf<String, MockRequestHandleScope.(HttpRequestData) -> HttpResponseData>()

    /** 디스크 대신 읽히는 파일. 프로젝트 jobs의 폴더는 `/work/jobs`다. */
    private val disk = mutableMapOf<String, String>()

    private val request = BlockHeader(
        id = "b01",
        type = BlockType.MESSAGE,
        role = MessageRole.USER,
        text = "경력 요약 고쳐줘",
        target = Target(block = "b05")
    )

    private var resume = PageDetail(
        id = "resume",
        project = "jobs",
        title = "이력서",
        status = Home.resume.status,
        pinned = true,
        tags = emptyList(),
        blocks = listOf(request),
        runs = listOf(
            RunRecord(
                n = 1,
                usage = RunUsage(input = 1, cached = 0, output = 1),
                changedFiles = listOf("page.md"),
                unknownFiles = emptyList(),
                verify = RunVerify(ok = true),
                trigger = RunTrigger(message = "b01"),
                finished = "2026-09-24T10:00:00+09:00",
                resultStatus = RunResultStatus.DONE
            )
        ),
        unknownFiles = emptyList()
    )

    private val files = object : LocalFiles {
        override suspend fun read(path: String): String =
            disk[path] ?: throw IllegalStateException("no $path")

        override fun openExternally(target: String) = Unit
    }

    private fun TestScope.openResume(
        settings: InMemorySettingsStore = InMemorySettingsStore()
    ): Pair<MainViewModel, MockCore> {
        val mock = MockCore(this) { request ->
            val key = "${request.method.value} ${request.url.encodedPath}"
            routes[key]?.invoke(this, request) ?: defaultResponse(request)
        }
        val transport = EventTransport { onOpen, onFrame ->
            onOpen()
            for (frame in events) onFrame(frame)
            awaitCancellation()
        }
        val viewModel = MainViewModel(
            CoreClient("http://core", mock.engine),
            EventStream(transport),
            backgroundScope,
            settings = settings,
            files = files
        )
        runCurrent()
        viewModel.select(ListSource.InProject("jobs"))
        viewModel.openPage("resume")
        runCurrent()
        return viewModel to mock
    }

    private fun MockRequestHandleScope.defaultResponse(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath
        return when {
            path == "/projects" ->
                json(codec.encodeToString(ListSerializer(Project.serializer()), Home.projects))

            path.startsWith("/projects/") && path.endsWith("/pages") -> {
                val id = path.removePrefix("/projects/").removeSuffix("/pages")
                val cards = Home.cards.filter { it.project == id }
                json(codec.encodeToString(ListSerializer(PageCard.serializer()), cards))
            }

            path == "/pages/resume" -> json(codec.encodeToString(PageDetail.serializer(), resume))

            else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
        }
    }

    private suspend fun event(
        type: String,
        data: String,
        run: Int? = null,
        page: String = "resume",
        block: String? = null
    ) {
        val fields = listOfNotNull(
            run?.let { ""","run":$it""" },
            block?.let { ""","block":"$it"""" }
        ).joinToString("")
        events.send(
            """{"type":"$type","ts":"t","project":"jobs","page":"$page"$fields,"data":$data}"""
        )
    }

    private fun MainViewModel.open(): OpenPage = assertNotNull(state.value.page)

    @Test
    fun resultBlockReadsTheRecordedMergeAndPublish() = runTest {
        disk["/work/jobs/.madang/pages/resume/runs/1.undo.json"] =
            """{"n":1,"effects":[{"kind":"merge","commit":"7b8c9d0e1f2a"},{"kind":"publish","publish":4}]}"""
        val (viewModel, _) = openResume()

        val outcome = assertNotNull(viewModel.open().outcome)

        assertEquals(1, outcome.n)
        assertEquals(SettleState.DONE, outcome.settle)
        assertEquals("7b8c9d0e1f2a", outcome.merged)
        assertEquals(4, outcome.published)
    }

    @Test
    fun publishEventTurnsAPendingResultDone() = runTest {
        val (viewModel, _) = openResume()

        resume = resume.copy(busy = true)
        event("run.finished", FINISHED_JSON, run = 1)
        runCurrent()
        assertEquals(SettleState.PENDING, viewModel.open().outcome?.settle)

        resume = resume.copy(busy = false)
        event("publish.done", """{"n":2,"undo":false}""", run = 1)
        runCurrent()
        val outcome = assertNotNull(viewModel.open().outcome)
        assertEquals(SettleState.DONE, outcome.settle)
        assertEquals(2, outcome.published)
    }

    @Test
    fun undoGoesToCoreOnceAndMarksTheResultUndone() = runTest {
        routes["POST /pages/resume/runs/1/undo"] = {
            json(
                """{"run":1,"restored":["page.md"],"skipped":[],"reverted":["9f8e"],"unpublished":[4]}"""
            )
        }
        val (viewModel, mock) = openResume()

        viewModel.undo()
        assertTrue(viewModel.open().undoing)
        viewModel.undo()
        runCurrent()

        val undos = mock.requests.filter { it.first == "POST /pages/resume/runs/1/undo" }
        assertEquals(1, undos.size)
        val open = viewModel.open()
        assertFalse(open.undoing)
        assertEquals(listOf(4), open.undoResult?.unpublished)
        assertTrue(assertNotNull(open.outcome).undone)

        viewModel.undo()
        runCurrent()
        assertEquals(1, mock.requests.count { it.first == "POST /pages/resume/runs/1/undo" })
    }

    @Test
    fun refusedUndoShowsTheReasonAndCanBeTriedAgain() = runTest {
        routes["POST /pages/resume/runs/1/undo"] = {
            json(
                """{"error":"conflict","message":"changed after the run"}""",
                HttpStatusCode.Conflict
            )
        }
        val (viewModel, _) = openResume()

        viewModel.undo()
        runCurrent()

        assertFalse(viewModel.open().undoing)
        assertFalse(assertNotNull(viewModel.open().outcome).undone)
        assertEquals("conflict: changed after the run", viewModel.state.value.loadError)
    }

    @Test
    fun rerunSendsTheSameRequestToTheSameTarget() = runTest {
        routes["POST /pages/resume/messages"] = {
            json("""{"message":"b02"}""", HttpStatusCode.Accepted)
        }
        val (viewModel, mock) = openResume()

        viewModel.rerun()
        runCurrent()

        assertTrue(
            "POST /pages/resume/messages" to
                """{"text":"경력 요약 고쳐줘","target":{"block":"b05"}}""" in mock.requests
        )
    }

    @Test
    fun rerunWaitsWhileARunIsGoing() = runTest {
        val (viewModel, mock) = openResume()
        event("run.started", RUN_STARTED_JSON, run = 2)
        runCurrent()

        viewModel.rerun()
        runCurrent()

        assertTrue(mock.requests.none { it.first.endsWith("/messages") })
    }

    @Test
    fun askBlockIsAnsweredThroughTheAskPath() = runTest {
        routes["POST /pages/resume/asks/b09/answer"] = { respond("", HttpStatusCode.Accepted) }
        val (viewModel, mock) = openResume()

        event("flow.waiting", ASK_WAITING_JSON, run = 1)
        event("ask.created", ASK_JSON, run = 1, block = "b09")
        runCurrent()
        assertEquals(SettleState.REFUSED, viewModel.open().outcome?.settle)

        viewModel.answer("merge")
        runCurrent()

        assertTrue(
            "POST /pages/resume/asks/b09/answer" to """{"choice":"merge"}""" in mock.requests
        )
        assertTrue(mock.requests.none { it.first.contains("/decisions/") })
    }

    @Test
    fun waitingAskAloneRefusesTheResult() = runTest {
        val (viewModel, _) = openResume()

        event("flow.waiting", ASK_WAITING_JSON, run = 1)
        runCurrent()

        assertEquals(SettleState.REFUSED, viewModel.open().outcome?.settle)
    }

    @Test
    fun busyDoesNotMarkAnOlderResultPendingWhileANewRunIsGoing() = runTest {
        val (viewModel, _) = openResume()

        resume = resume.copy(
            busy = true,
            runs = resume.runs + resume.runs.single().copy(
                n = 2,
                finished = null,
                resultStatus = null
            )
        )
        event("run.started", RUN_STARTED_JSON, run = 2)
        runCurrent()

        val outcome = assertNotNull(viewModel.open().outcome)
        assertEquals(1, outcome.n)
        assertNull(outcome.settle)
    }

    @Test
    fun unreadSurvivesARestart() = runTest {
        val settings = InMemorySettingsStore(AppSettings(unread = setOf("posting")))
        val (viewModel, _) = openResume(settings)
        assertTrue("posting" in viewModel.state.value.watch.unread)

        event("run.finished", FINISHED_JSON, run = 1, page = "cover")
        runCurrent()

        assertEquals(setOf("posting", "cover"), settings.load().unread)
    }

    @Test
    fun openingAPageClearsItsSavedUnread() = runTest {
        val settings = InMemorySettingsStore(AppSettings(unread = setOf("resume")))

        openResume(settings)

        assertNull(settings.load().unread.firstOrNull { it == "resume" })
    }

    private companion object {
        const val FINISHED_JSON = """{"n":1,"usage":{"input":1,"cached":0,"output":1},
            "changed_files":[],"unknown_files":[],"verify":{"ok":true},"result_status":"done"}"""

        const val RUN_STARTED_JSON =
            """{"runner":"claude","model":"claude-opus-5-5","kind":"build","tier":1}"""

        const val ASK_WAITING_JSON = """{"decision":{"id":"b08","run":1,"ask":"b09",
            "reasons":["테스트 실패(종료 코드 1)"],
            "question":{"kind":"choice","prompt":"정책이 머지를 멈췄습니다.","options":["merge","retry","stop"]}}}"""

        const val ASK_JSON = """{"block":"b09","decision":"b08","prompt":"정책이 머지를 멈췄습니다.",
            "reasons":["테스트 실패(종료 코드 1)"],"options":["merge","retry","stop"]}"""
    }
}
