package madang.shared.main

import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.Project
import madang.api.model.UnknownFileAction
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventTransport
import madang.shared.json

/**
 * 가짜 이벤트 스트림과 가짜 core로 3열의 상태 전이를 확인한다.
 *
 * 이벤트는 [events] 채널로 보내고, core 응답은 [handler]가 만든다. ViewModel은 backgroundScope에서
 * 돌므로 배경 작업까지 돌리려면 runCurrent를 쓴다.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PageEventsTest {

    private val codec = CoreClient.CoreJson
    private val events = Channel<String>(Channel.UNLIMITED)

    /** core가 가진 resume 페이지. 메시지를 받으면 블록이 늘어난다. */
    private var resume = PageDetail(
        id = "resume",
        project = "jobs",
        title = "이력서",
        status = Home.resume.status,
        pinned = true,
        tags = listOf("이력서"),
        blocks = listOf(user("b01", "이력서 템플릿 만들어줘")),
        runs = emptyList(),
        unknownFiles = emptyList()
    )

    /** 경로별 추가 응답. 없으면 [defaultResponse]. */
    private val routes =
        mutableMapOf<String, MockRequestHandleScope.(HttpRequestData) -> HttpResponseData>()

    /** `GET /preview-input`의 text 파라미터. */
    private val previewTexts = mutableListOf<String?>()

    private fun user(id: String, text: String) =
        BlockHeader(id = id, type = BlockType.MESSAGE, role = MessageRole.USER, text = text)

    private fun TestScope.openResume(): Pair<MainViewModel, MockCore> {
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
            backgroundScope
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

            path == "/pages/resume/preview-input" -> {
                previewTexts += request.url.parameters["text"]
                json(PREVIEW_JSON)
            }

            else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
        }
    }

    private suspend fun event(type: String, data: String, run: Int? = null) {
        val runField = run?.let { ""","run":$it""" }.orEmpty()
        events.send(
            """{"type":"$type","ts":"t","project":"jobs","page":"resume"$runField,"data":$data}"""
        )
    }

    private fun MainViewModel.open(): OpenPage = assertNotNull(state.value.page)

    @Test
    fun unknownFilesEventShowsBandAndEachActionShrinksTheList() = runTest {
        routes["POST /pages/resume/unknown-files/blocks%2Fnotes.txt"] = {
            json("""[{"path":"repo:src/scratch.ts","run":2}]""")
        }
        routes["POST /pages/resume/unknown-files/repo%3Asrc%2Fscratch.ts"] = { json("[]") }
        val (viewModel, mock) = openResume()

        event(
            "page.unknown_files",
            """{"files":[{"path":"blocks/notes.txt","run":2},{"path":"repo:src/scratch.ts","run":2}]}""",
            run = 2
        )
        runCurrent()
        assertEquals(2, viewModel.open().detail.unknownFiles.size)

        viewModel.showUnknownFiles(true)
        viewModel.resolveUnknownFile("blocks/notes.txt", UnknownFileAction.Action.ARTIFACT)
        runCurrent()
        assertTrue(
            "POST /pages/resume/unknown-files/blocks%2Fnotes.txt" to """{"action":"artifact"}""" in
                mock.requests
        )
        assertEquals(
            listOf("repo:src/scratch.ts"),
            viewModel.open().detail.unknownFiles.map {
                it.path
            }
        )
        assertTrue(viewModel.state.value.unknownFilesOpen)

        viewModel.resolveUnknownFile("repo:src/scratch.ts", UnknownFileAction.Action.DELETE)
        runCurrent()
        assertTrue(viewModel.open().detail.unknownFiles.isEmpty())
        assertFalse(viewModel.state.value.unknownFilesOpen)
    }

    @Test
    fun unknownFilesListDoesNotOpenWhenEmpty() = runTest {
        val (viewModel, _) = openResume()

        viewModel.showUnknownFiles(true)

        assertFalse(viewModel.state.value.unknownFilesOpen)
    }

    @Test
    fun flowWaitingShowsDecisionAndAnswerResumesOnce() = runTest {
        routes["POST /pages/resume/decisions/q1/answer"] = { respond("", HttpStatusCode.Accepted) }
        val (viewModel, mock) = openResume()

        event("flow.waiting", WAITING_JSON, run = 2)
        runCurrent()
        val decision = assertNotNull(viewModel.open().detail.waiting?.decision)
        assertEquals("q1", decision.id)
        assertEquals(listOf("retry", "next_tier", "stop"), decision.question.options)

        viewModel.answer("retry")
        viewModel.answer("stop")
        runCurrent()
        val answers = mock.requests.filter { it.first == "POST /pages/resume/decisions/q1/answer" }
        assertEquals(listOf("""{"choice":"retry"}"""), answers.map { it.second })
        assertEquals("q1", viewModel.open().answered)

        event("run.started", RUN_STARTED_JSON, run = 3)
        runCurrent()
        assertNull(viewModel.open().detail.waiting)
        assertNull(viewModel.open().answered)
    }

    @Test
    fun failedAnswerLetsTheUserAnswerAgain() = runTest {
        routes["POST /pages/resume/decisions/q1/answer"] = {
            json("""{"error":"conflict","message":"not waiting"}""", HttpStatusCode.Conflict)
        }
        val (viewModel, _) = openResume()
        event("flow.waiting", WAITING_JSON, run = 2)
        runCurrent()

        viewModel.answer("retry")
        runCurrent()

        assertNull(viewModel.open().answered)
        assertEquals("conflict: not waiting", viewModel.state.value.loadError)
    }

    @Test
    fun waitingWithoutDecisionShowsReasonOnly() = runTest {
        val (viewModel, mock) = openResume()

        event("flow.waiting", """{"reason":"no_runner"}""")
        runCurrent()
        viewModel.answer("retry")
        runCurrent()

        assertEquals("no_runner", viewModel.open().detail.waiting?.reason)
        assertTrue(mock.requests.none { it.first.contains("/decisions/") })
    }

    @Test
    fun sentMessageAppearsAtOnceAndIsReplacedByTheCoreBlock() = runTest {
        routes["POST /pages/resume/messages"] = {
            resume = resume.copy(blocks = resume.blocks + user("b02", "design: 표 만들어줘"))
            json("""{"message":"b02"}""", HttpStatusCode.Accepted)
        }
        val (viewModel, mock) = openResume()

        viewModel.composer.setText("design: 표 만들어줘")
        viewModel.send()

        val pending = viewModel.open().flowItems.last()
        assertIs<FlowItem.Pending>(pending)
        assertEquals("design: 표 만들어줘", pending.message.text)
        assertEquals("", viewModel.composer.state.value.text)

        runCurrent()
        assertTrue(
            "POST /pages/resume/messages" to """{"text":"design: 표 만들어줘"}""" in mock.requests
        )
        assertEquals("b02", viewModel.open().pending.single().messageId)

        events.send(
            """{"type":"block.added","ts":"t","project":"jobs","page":"resume","block":"b02",""" +
                """"data":{"block":{"id":"b02","type":"message"}}}"""
        )
        runCurrent()
        val items = viewModel.open().flowItems
        assertEquals(listOf("b01", "b02"), items.map { it.key })
        assertTrue(viewModel.open().pending.isEmpty())
    }

    @Test
    fun failedSendRemovesTheMessageAndRestoresTheText() = runTest {
        routes["POST /pages/resume/messages"] = {
            json("""{"error":"conflict","message":"run in progress"}""", HttpStatusCode.Conflict)
        }
        val (viewModel, _) = openResume()

        viewModel.composer.setText("다시 해줘")
        viewModel.send()
        runCurrent()

        assertTrue(viewModel.open().flowItems.none { it is FlowItem.Pending })
        assertEquals("다시 해줘", viewModel.composer.state.value.text)
        assertEquals("conflict: run in progress", viewModel.state.value.loadError)
    }

    @Test
    fun blankTextIsNotSent() = runTest {
        val (viewModel, mock) = openResume()

        viewModel.composer.setText("   ")
        viewModel.send()
        runCurrent()

        assertTrue(mock.requests.none { it.first.endsWith("/messages") })
    }

    @Test
    fun runEventsShowProgressUntilTheRunEnds() = runTest {
        val (viewModel, _) = openResume()

        event("run.started", RUN_STARTED_JSON, run = 3)
        event("run.assembled", """{"parts":$PARTS_JSON,"total_est":29230}""", run = 3)
        runCurrent()
        val run = assertNotNull(viewModel.state.value.activeRuns["resume"])
        assertEquals(RunActivity.Assembled(29230), run.last)

        event("run.failed", """{"result_status":"cancelled","error":"cancelled"}""", run = 3)
        runCurrent()
        assertNull(viewModel.state.value.activeRuns["resume"])
    }

    @Test
    fun inputPreviewIsDebouncedWhileTyping() = runTest {
        val (viewModel, _) = openResume()
        advanceTimeBy(ComposerViewModel.PREVIEW_DEBOUNCE.inWholeMilliseconds + 1)
        runCurrent()
        previewTexts.clear()

        viewModel.composer.setText("표")
        advanceTimeBy(200)
        viewModel.composer.setText("표 만들어")
        advanceTimeBy(299)
        runCurrent()
        assertTrue(previewTexts.isEmpty())

        advanceTimeBy(2)
        runCurrent()
        assertEquals(listOf<String?>("표 만들어"), previewTexts)
        assertEquals(29230, viewModel.composer.state.value.preview?.totalEst)
    }

    @Test
    fun composerFollowsTheOpenPage() = runTest {
        val (viewModel, _) = openResume()
        assertEquals("resume", viewModel.composer.state.value.page)

        viewModel.composer.setText("쓰던 문장")
        event("page.deleted", """{"id":"resume"}""")
        runCurrent()

        assertNull(viewModel.composer.state.value.page)
        assertEquals("", viewModel.composer.state.value.text)
    }

    @Test
    fun memoryUpdatedEventReloadsTheOpenPanel() = runTest {
        routes["GET /pages/resume/memory"] = { json(MEMORY_JSON) }
        val (viewModel, mock) = openResume()

        viewModel.toggleMemory()
        runCurrent()
        assertTrue(viewModel.memory.state.value.isOpen)
        event("memory.updated", """{"layer":"profile","tokens":20}""")
        runCurrent()

        assertEquals(2, mock.requests.count { it.first == "GET /pages/resume/memory" })
        viewModel.toggleMemory()
        assertFalse(viewModel.memory.state.value.isOpen)
    }

    @Test
    fun responseAndEventForTheSamePageKeepOneCard() = runTest {
        val created = Home.draft.copy(id = "new", project = "jobs", title = "새 페이지")
        routes["POST /projects/jobs/pages"] = {
            json(
                codec.encodeToString(
                    PageDetail.serializer(),
                    resume.copy(id = "new", title = "새 페이지", blocks = emptyList())
                ),
                HttpStatusCode.Created
            )
        }
        val (viewModel, _) = openResume()

        viewModel.newPage()
        runCurrent()
        val card = codec.encodeToString(PageCard.serializer(), created)
        events.send(
            """{"type":"page.created","ts":"t","project":"jobs","page":"new","data":{"page":$card}}"""
        )
        events.send(
            """{"type":"page.created","ts":"t","project":"jobs","page":"new","data":{"page":$card}}"""
        )
        runCurrent()

        assertEquals(1, viewModel.state.value.cards.count { it.id == "new" })
    }

    private companion object {
        const val PARTS_JSON =
            """{"system_est":24600,"profile":110,"brief":1840,"ledger":1320,"contract":420,"target":900,"request":40}"""

        const val PREVIEW_JSON =
            """{"kind":"small","tier":1,"runner":"codex","model":"gpt-6-luna","parts":$PARTS_JSON,"total_est":29230}"""

        const val RUN_STARTED_JSON =
            """{"runner":"codex","model":"gpt-6-luna","kind":"small","tier":1,"trigger":{"message":"b01"}}"""

        const val WAITING_JSON =
            """{"decision":{"id":"q1","run":2,"question":{"kind":"choice","prompt":"어떻게 할까요?","options":["retry","next_tier","stop"]}}}"""

        const val MEMORY_JSON = """{
            "profile":{"layer":"profile","path":"profile.md","content":"# 나\n","tokens":3},
            "brief":{"layer":"brief","path":"projects/jobs/brief.md","content":"지원\n","tokens":2},
            "ledger":{"layer":"ledger","path":"ledger.md","content":"---\nstatus: review\n---\n","tokens":9,"token_limit":2000}}"""
    }
}
