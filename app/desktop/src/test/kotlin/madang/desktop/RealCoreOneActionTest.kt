package madang.desktop

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.WebSocketEventTransport
import madang.shared.main.ListSource
import madang.shared.main.MainState
import madang.shared.main.MainViewModel
import madang.shared.main.SettleState

/**
 * 떠 있는 실제 core로 한 동작을 끝까지 돌린다: 문서 페이지에 요청을 보내고, 결과 블록이 게시 상태를
 * 보이고, 되돌리기로 게시를 되감는지. 화면 없이 앱의 상태만 본다.
 *
 * 실제 에이전트 호출이 한 번 들기 때문에 `MADANG_REAL_CORE_URL`이 있을 때만 돈다. 함께 주는 값:
 * `MADANG_REAL_PROJECT`(프로젝트 id), `MADANG_REAL_PAGE`(페이지 id), `MADANG_REAL_REQUEST`(요청),
 * 선택 `MADANG_REAL_LOG`(본 상태를 적을 파일).
 */
class RealCoreOneActionTest {

    private val url: String? = System.getenv("MADANG_REAL_CORE_URL")
    private val log = mutableListOf<String>()

    @Test
    fun sendShowsThePublishStateAndUndoRewindsIt() {
        val base = url ?: return
        val project = checkNotNull(System.getenv("MADANG_REAL_PROJECT"))
        val page = checkNotNull(System.getenv("MADANG_REAL_PAGE"))
        val request = checkNotNull(System.getenv("MADANG_REAL_REQUEST"))
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val core = CoreClient(base)
        try {
            val events = EventStream(WebSocketEventTransport(core.http, core.baseUrl))
            val main = MainViewModel(core, events, scope, files = DesktopLocalFiles())
            runBlocking { playOnce(main, project, page, request) }
        } finally {
            scope.cancel()
            core.close()
            System.getenv("MADANG_REAL_LOG")?.let {
                File(it).writeText(log.joinToString("\n", postfix = "\n"))
            }
        }
    }

    private suspend fun playOnce(
        main: MainViewModel,
        project: String,
        page: String,
        request: String
    ) {
        main.select(ListSource.InProject(project))
        main.openPage(page)
        val before = waitFor(main, OPEN_TIMEOUT) { it.page?.detail?.id == page }
        val runsBefore = before.page?.detail?.runs.orEmpty().size
        note("opened $page, runs=$runsBefore, outcome=${before.page?.outcome}")

        main.composer.setText(request)
        main.send()
        note("sent: $request")
        var seen = ""
        val settled = waitFor(main, RUN_TIMEOUT) { state ->
            val open = state.page ?: return@waitFor false
            val outcome = open.outcome?.takeIf { open.detail.runs.size > runsBefore }
            val running = page in state.activeRuns
            val waiting = open.detail.waiting
            val shown = "running=$running status=${open.detail.status.value} " +
                "result=${outcome?.n} settle=${outcome?.settle} published=${outcome?.published} " +
                "waiting=${waiting?.reason ?: waiting?.decision?.question?.prompt}"
            if (shown != seen) {
                seen = shown
                note(shown)
            }
            !running &&
                (waiting != null || outcome?.settle.let { it != null && it != SettleState.PENDING })
        }
        val outcome = assertNotNull(settled.page?.outcome)
        note("final: $outcome")
        assertEquals(SettleState.DONE, outcome.settle)
        assertNotNull(outcome.published)

        main.undo()
        note("undo sent for run ${outcome.n}")
        val undone = waitFor(main, OPEN_TIMEOUT) {
            it.page?.undoResult != null && it.page?.outcome?.undone == true
        }
        note("undo result: ${undone.page?.undoResult}")
        note("after undo: ${undone.page?.outcome}")
        assertTrue(undone.page?.undoResult?.unpublished.orEmpty().isNotEmpty())
        undone.loadError?.let { note("status line: $it") }
    }

    private suspend fun waitFor(
        main: MainViewModel,
        timeout: Duration,
        done: (MainState) -> Boolean
    ): MainState = withTimeout(timeout) {
        while (!done(main.state.value)) delay(POLL)
        main.state.value
    }

    private fun note(line: String) {
        val stamped = "${java.time.LocalTime.now().withNano(0)} $line"
        log += stamped
        println("real-core: $stamped")
    }

    private companion object {
        val POLL = 200.milliseconds
        val OPEN_TIMEOUT = 1.minutes
        val RUN_TIMEOUT = 15.minutes
    }
}
