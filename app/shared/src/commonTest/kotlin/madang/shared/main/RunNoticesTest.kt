package madang.shared.main

import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import madang.api.model.PageCard
import madang.api.model.Project
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventTransport
import madang.shared.json
import madang.shared.settings.AppSettings
import madang.shared.settings.InMemorySettingsStore

/** run 이벤트가 카드의 읽지 않음·글리프와 시스템 알림으로 이어지는지. */
@OptIn(ExperimentalCoroutinesApi::class)
class RunNoticesTest {

    private val codec = CoreClient.CoreJson
    private val events = Channel<String>(Channel.UNLIMITED)

    private fun TestScope.mainWith(
        settings: AppSettings = AppSettings()
    ): Pair<MainViewModel, List<Notice>> {
        val mock = MockCore(this) { request ->
            val path = request.url.encodedPath
            when {
                path == "/projects" ->
                    json(codec.encodeToString(ListSerializer(Project.serializer()), Home.projects))

                path.endsWith("/pages") -> {
                    val id = path.removePrefix("/projects/").removeSuffix("/pages")
                    val cards = Home.cards.filter { it.project == id }
                    json(codec.encodeToString(ListSerializer(PageCard.serializer()), cards))
                }

                else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
            }
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
            settings = InMemorySettingsStore(settings)
        )
        val received = mutableListOf<Notice>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            viewModel.notices.collect { received += it }
        }
        runCurrent()
        return viewModel to received
    }

    private suspend fun event(type: String, page: String, data: String, run: Int? = null) {
        val runField = run?.let { ""","run":$it""" }.orEmpty()
        events.send(
            """{"type":"$type","ts":"2026-09-24T12:00:00+09:00","project":"jobs","page":"$page"""" +
                """$runField,"data":$data}"""
        )
    }

    @Test
    fun finishedRunMakesTheCardUnreadAndNotifies() = runTest {
        val (viewModel, received) = mainWith()

        event("run.finished", "posting", FINISHED_JSON, run = 1)
        runCurrent()

        val state = viewModel.state.value
        assertTrue("posting" in state.watch.unread)
        assertEquals(RunGlyph.DONE, state.glyphOf("posting"))
        val notice = assertIs<Notice.Finished>(received.single())
        assertEquals("공고 분석", notice.title)
    }

    @Test
    fun theSameQuestionIsNotifiedOnce() = runTest {
        val (viewModel, received) = mainWith()

        event("ask.created", "resume", ASK_JSON)
        event("flow.waiting", "resume", WAITING_JSON)
        runCurrent()

        assertEquals(1, received.size)
        assertEquals("게시할까요?", assertIs<Notice.Asked>(received.single()).prompt)
        assertEquals(RunGlyph.NEEDS_HUMAN, viewModel.state.value.glyphOf("resume"))
    }

    @Test
    fun notificationsCanBeTurnedOff() = runTest {
        val (_, received) = mainWith(AppSettings(notifications = false))

        event("run.failed", "resume", """{"result_status":"error","error":"boom"}""", run = 2)
        runCurrent()

        assertTrue(received.isEmpty())
    }

    private companion object {
        const val FINISHED_JSON = """{"n":1,"usage":{"input":1,"cached":0,"output":1},
            "changed_files":[],"unknown_files":[],"verify":{},"result_status":"review"}"""
        const val ASK_JSON = """{"block":"b09","decision":"q1","prompt":"게시할까요?",
            "reasons":["auto_publish off"],"options":["yes","no"]}"""
        const val WAITING_JSON = """{"decision":{"id":"q1",
            "question":{"kind":"choice","prompt":"게시할까요?","options":["yes","no"]}}}"""
    }
}
