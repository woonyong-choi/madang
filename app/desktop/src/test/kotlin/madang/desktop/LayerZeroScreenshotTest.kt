package madang.desktop

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.ImageComposeScene
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Density
import java.io.File
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlin.time.Clock
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.datetime.TimeZone
import madang.api.model.FileLens
import madang.api.model.FileTree
import madang.api.model.MemoryLayer
import madang.desktop.fake.ContractExamples
import madang.desktop.fake.FakeCore
import madang.desktop.fake.FixtureHome
import madang.shared.BrowserEngine
import madang.shared.BrowserStatus
import madang.shared.LocalBrowserEngine
import madang.shared.NoBrowserEngine
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.main.CenterTab
import madang.shared.main.DiffView
import madang.shared.main.FlowItem
import madang.shared.main.GitView
import madang.shared.main.ListSource
import madang.shared.main.Load
import madang.shared.main.MEMORY_ORDER
import madang.shared.main.MainState
import madang.shared.main.MainViewModel
import madang.shared.main.MemoryDraft
import madang.shared.main.OpenRequest
import madang.shared.main.Pane
import madang.shared.main.RunGlyph
import madang.shared.main.SideTab
import madang.shared.main.TAB_BLOCK_TYPES
import madang.shared.main.TabKind
import madang.shared.main.kindOf
import madang.shared.main.placeIssues
import madang.shared.main.splitMemory
import madang.shared.ui.KoreanStrings
import madang.shared.ui.ListClock
import madang.shared.ui.LocalListClock
import madang.shared.ui.LocalStrings
import madang.shared.ui.MainScreen
import org.jetbrains.skia.EncodedImageFormat

/**
 * 픽스처 앱 홈으로 레이어 0을 화면 밖에서 그려 PNG로 남긴다.
 *
 * 넓은 창(3열), 좁은 창(목록 + 본문 2열), 더 좁은 창(본문 1열)과, 메시지를 보내 run 카드가 붙고
 * 미등록 파일 띠·사람 결정 카드·메모리 검사 오류가 보이는 화면, 가운데 열의 페이지 탭과 run 탭,
 * 오른쪽 사이드바의 메모리 탭(Profile / Brief / Ledger와 머리부 폼의 검사 오류)과 지금·파일·git·포트 탭을
 * 그린다. 결과는 `madang.screenshotDir`(기본 `build/screenshots`)에 쓴다.
 */
class LayerZeroScreenshotTest {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val outDir = File(System.getProperty("madang.screenshotDir") ?: "build/screenshots")

    private val clock = ListClock(
        now = { Instant.parse("2026-09-24T12:00:00+09:00") },
        zone = TimeZone.of("Asia/Seoul")
    )

    @AfterTest
    fun tearDown() = scope.cancel()

    private fun viewModel(runStep: Duration = 600.milliseconds): MainViewModel {
        val spec = File(checkNotNull(System.getProperty("madang.openapiSpec")))
        val home = File(checkNotNull(javaClass.getResource("/fixture-home")).toURI())
        val fixture = FixtureHome(home, runStep)
        val fake = FakeCore(ContractExamples.load(spec), homeReady = true, fixture = fixture)
        val core = CoreClient(CoreClient.DEFAULT_BASE_URL, fake.engine)
        return MainViewModel(core, EventStream(fake.events), scope, "제목 없음")
    }

    private fun MainViewModel.await(condition: (MainState) -> Boolean): MainState = runBlocking {
        withTimeout(10.seconds) { state.first(condition) }
    }

    private fun MainViewModel.show(project: String, page: String, pane: Pane) {
        select(ListSource.InProject(project))
        openPage(page)
        await { it.page?.detail?.id == page && it.page?.contents?.size == docAndDataCount(it) }
        focusPane(pane)
    }

    private fun docAndDataCount(state: MainState): Int =
        state.page?.detail?.blocks?.count { it.type in TAB_BLOCK_TYPES } ?: 0

    /** 화면 밖 장면 하나. 프레임을 흘려 보내고 지금 화면을 PNG로 남긴다. */
    private inner class OffscreenMain(
        widthDp: Int,
        heightDp: Int,
        viewModel: MainViewModel,
        browser: BrowserEngine = NoBrowserEngine,
        listClock: ListClock = clock
    ) : AutoCloseable {
        private val density = 2f
        private val scene = ImageComposeScene(
            width = (widthDp * density).toInt(),
            height = (heightDp * density).toInt(),
            density = Density(density)
        ) {
            CompositionLocalProvider(
                LocalStrings provides KoreanStrings,
                LocalListClock provides listClock,
                LocalBrowserEngine provides browser
            ) {
                MaterialTheme { Surface { MainScreen(viewModel) {} } }
            }
        }
        private var frames = 0L
        private var last = scene.render(0)

        /** 상태 변화와 애니메이션이 화면에 반영되도록 프레임을 몇 장 그린다. */
        fun settle() {
            repeat(FRAMES) {
                Thread.sleep(FRAME_GAP_MS)
                last = scene.render(++frames * FRAME_GAP_MS * 1_000_000)
            }
        }

        fun save(name: String): File {
            val png = checkNotNull(last.encodeToData(EncodedImageFormat.PNG)).bytes
            outDir.mkdirs()
            return File(outDir, "$name.png").apply { writeBytes(png) }
        }

        override fun close() = scene.close()
    }

    private fun render(
        name: String,
        widthDp: Int,
        heightDp: Int,
        viewModel: MainViewModel,
        browser: BrowserEngine = NoBrowserEngine
    ): File = OffscreenMain(widthDp, heightDp, viewModel, browser).use {
        it.settle()
        it.save(name)
    }

    @Test
    fun rendersWideNarrowAndSinglePageLayouts() {
        val viewModel = viewModel()
        val loaded = viewModel.await { it.loaded && it.activeRuns.isNotEmpty() }
        assertEquals(5, loaded.projects.size)
        assertEquals(9, loaded.cards.size)

        viewModel.show("jobs", "2026-09-24-resume", Pane.LIST)
        val wide = render("wide", 1440, 900, viewModel)

        viewModel.show("jobs-2026", "2026-09-20-cover-letter", Pane.PAGE)
        val narrow = render("narrow", 960, 760, viewModel)

        viewModel.show("auth-svc", "2026-09-24-session-bug", Pane.PAGE)
        val page = render("page", 620, 1000, viewModel)

        for (file in listOf(wide, narrow, page)) assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun sentMessageGrowsIntoARunCard() {
        val viewModel = viewModel(runStep = 1.seconds)
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)
        val runsBefore = checkNotNull(viewModel.state.value.page).detail.runs.size

        OffscreenMain(1100, 900, viewModel).use { screen ->
            screen.settle()
            viewModel.composer.setText("design: 경력 요약을 한 줄 더 붙여줘")
            viewModel.send()
            val sending = viewModel.state.value.page?.flowItems?.last()
            assertIs<FlowItem.Pending>(sending)

            viewModel.await { it.activeRuns[RESUME] != null }
            screen.settle()
            screen.save("message-running")

            val done = viewModel.await {
                it.activeRuns[RESUME] == null && it.page?.detail?.runs?.size == runsBefore + 1
            }
            val items = checkNotNull(done.page).flowItems
            assertTrue(items.none { it is FlowItem.Pending })
            val runIndex = items.indexOfLast { it is FlowItem.Run }
            val message = items[runIndex - 1]
            assertIs<FlowItem.Block>(message)
            assertEquals("design: 경력 요약을 한 줄 더 붙여줘", message.header.text)
            assertEquals(1, done.page?.detail?.unknownFiles?.size)
            screen.settle()
            val file = screen.save("message-done")
            assertTrue(file.length() > 10_000, file.path)
        }
    }

    @Test
    fun decisionCardAndMemoryErrorsAreShown() {
        val viewModel = viewModel(runStep = 50.milliseconds)
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)

        viewModel.composer.setText("결정이 필요한 요청")
        viewModel.send()
        viewModel.await { it.page?.detail?.waiting?.decision != null }

        val rejected = rejectLedgerStatus(viewModel)
        assertEquals(setOf(2), rejected.issuesByLine.keys)

        val file = render("decision-memory", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun memoryTabShowsLayersInOrderWithInlineErrors() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)

        val rejected = rejectLedgerStatus(viewModel)
        val memory = viewModel.memory.state.value
        assertEquals(MEMORY_ORDER, memory.ordered.map { it.file.layer })
        assertEquals(SideTab.MEMORY, viewModel.state.value.sidebar.tab)
        val parts = splitMemory(rejected.text)
        val status = parts.fields.first { it.key == "status" }
        assertEquals(
            listOf(2),
            placeIssues(parts, rejected.issues).byField[status.line]?.map {
                it.line
            }
        )

        val file = render("memory-tab", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    /** 메모리 탭을 열고 Ledger의 status를 틀린 값으로 저장해 검사 오류를 받는다. */
    private fun rejectLedgerStatus(viewModel: MainViewModel): MemoryDraft {
        viewModel.toggleMemory()
        val memory = viewModel.memory.state
        runBlocking { withTimeout(10.seconds) { memory.first { it.ordered.size == 3 } } }
        viewModel.memory.editField(MemoryLayer.LEDGER, "status", "finished")
        viewModel.memory.save(MemoryLayer.LEDGER)
        val rejected = runBlocking {
            withTimeout(10.seconds) {
                memory.first { it.drafts[MemoryLayer.LEDGER]?.issues?.isNotEmpty() == true }
            }
        }
        return checkNotNull(rejected.drafts[MemoryLayer.LEDGER])
    }

    @Test
    fun centerColumnShowsPageAndRunTabs() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)
        val flow = checkNotNull(viewModel.state.value.page).flowItems
        viewModel.openItem(flow.first { it.key == "b05" })
        viewModel.openItem(flow.first { it.key == "run-2" })
        viewModel.activateTab(null)
        val page = render("tabs-page", 1440, 900, viewModel)

        viewModel.openItem(flow.first { it.key == "run-2" })
        val withEvents = viewModel.await { it.page?.runEvents?.get(2)?.isNotEmpty() == true }
        assertEquals(listOf(CenterTab.Block("b05"), CenterTab.Run(2)), withEvents.tabs.tabs)
        assertEquals(CenterTab.Run(2), withEvents.tabs.active)
        val run = render("tabs-run", 1440, 900, viewModel)

        for (file in listOf(page, run)) assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun dataTabShowsTheBlockAsATable() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("auth-svc", SESSION_BUG, Pane.PAGE)
        val flow = checkNotNull(viewModel.state.value.page).flowItems
        viewModel.openItem(flow.first { it.key == "b05" })

        val state = viewModel.state.value
        assertEquals(TabKind.DATA, kindOf(state.tabs.active, checkNotNull(state.page).detail))
        val file = render("tabs-data", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun diffTabShowsCoreDiffByFile() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("auth-svc", SESSION_BUG, Pane.PAGE)
        viewModel.open(OpenRequest.Diff)

        val loaded = viewModel.await { it.page?.diff is Load.Ready }
        val diff = assertIs<Load.Ready<DiffView>>(loaded.page?.diff).value
        assertEquals(
            listOf("src/session/refresh.ts", "src/session/lock.ts", "src/session/legacy-retry.ts"),
            diff.files.map { it.path }
        )
        val file = render("tabs-diff", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun browserTabShowsTheFirstRunDownload() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)
        viewModel.open(OpenRequest.Url("http://localhost:5173"))
        val engine = DownloadingEngine()

        assertEquals(CenterTab.Browser("http://localhost:5173"), viewModel.state.value.tabs.active)
        val file = render("tabs-browser", 1440, 900, viewModel, engine)
        assertTrue(engine.prepared)
        assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun nowTabShowsRunningAndUnreadRunsWithUsage() {
        val viewModel = viewModel(runStep = 300.milliseconds)
        viewModel.await { it.loaded && it.activeRuns.isNotEmpty() }
        viewModel.show("jobs", RESUME, Pane.PAGE)
        viewModel.composer.setText("design: 경력 요약을 한 줄 더 붙여줘")
        viewModel.send()
        viewModel.await { it.activeRuns[RESUME] != null }
        viewModel.show("auth-svc", SESSION_BUG, Pane.PAGE)
        val done = viewModel.await { it.activeRuns[RESUME] == null && RESUME in it.watch.unread }
        assertEquals(RunGlyph.DONE, done.glyphOf(RESUME))

        viewModel.selectSideTab(SideTab.NOW)
        val now = viewModel.side.now.state
        runBlocking { withTimeout(10.seconds) { now.first { it.usage is Load.Ready } } }
        val realClock = ListClock(now = { Clock.System.now() }, zone = clock.zone)
        val items = done.nowItems(realClock.now())
        assertEquals(RunGlyph.RUNNING, items.first().glyph)
        val resume = items.first { it.page == RESUME }
        assertTrue(resume.unread)
        viewModel.side.now.showInput(resume)
        viewModel.side.now.toggleLog(items.first())
        runBlocking {
            withTimeout(10.seconds) {
                now.first { it.input?.second is Load.Ready && it.log?.second is Load.Ready }
            }
        }
        val file = OffscreenMain(1440, 900, viewModel, listClock = realClock).use {
            it.settle()
            it.save("side-now")
        }
        assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun filesTabShowsTheTreeWithDeclaredRunBadgesOnly() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("auth-svc", SESSION_BUG, Pane.PAGE)
        viewModel.selectSideTab(SideTab.FILES)
        val files = viewModel.side.files.state
        val loaded =
            runBlocking { withTimeout(10.seconds) { files.first { it.tree is Load.Ready } } }
        assertEquals(".madang", loaded.rows.first().path)
        assertFalse(loaded.rows.first().expanded)
        assertTrue(loaded.rows.all { it.runs.isEmpty() })
        assertEquals(listOf("api 서버"), assertIs<Load.Ready<FileTree>>(loaded.tree).value.runs)

        val file = render("side-files", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)

        viewModel.side.files.setLens(FileLens.PAGE)
        val page = runBlocking {
            withTimeout(10.seconds) {
                files.first { it.lens == FileLens.PAGE && it.tree is Load.Ready }
            }
        }
        assertEquals(
            listOf("src", "src/session", "src/session/lock.ts", "src/session/refresh.ts"),
            page.rows.map { it.path }
        )
    }

    @Test
    fun gitTabShowsTheRepositoryAndOnlyGitInitElsewhere() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)
        viewModel.selectSideTab(SideTab.GIT)
        val git = viewModel.side.git.state
        val plain = runBlocking { withTimeout(10.seconds) { git.first { it.view is Load.Ready } } }
        assertFalse(assertIs<Load.Ready<GitView>>(plain.view).value.repository)

        viewModel.show("auth-svc", SESSION_BUG, Pane.PAGE)
        val repo = runBlocking {
            withTimeout(10.seconds) {
                git.first { (it.view as? Load.Ready)?.value?.repository == true }
            }
        }
        val view = assertIs<Load.Ready<GitView>>(repo.view).value
        assertEquals(SESSION_BUG, view.worktrees.last().page)
        assertEquals(3, view.log.size)
        viewModel.side.git.stage(listOf("src/session/lock.ts"))
        runBlocking {
            withTimeout(10.seconds) {
                git.first { state ->
                    val files = (state.view as? Load.Ready)?.value?.status?.files.orEmpty()
                    files.any { it.path == "src/session/lock.ts" && it.code == "M " }
                }
            }
        }
        viewModel.side.git.setMessage("fix(session): hold the refresh lock")
        val file = render("side-git", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    @Test
    fun portsTabSavesAnObservedPortAsADeclaration() {
        val viewModel = viewModel()
        viewModel.await { it.loaded }
        viewModel.show("jobs", RESUME, Pane.PAGE)
        viewModel.selectSideTab(SideTab.PORTS)
        val ports = viewModel.side.ports.state
        runBlocking { withTimeout(10.seconds) { ports.first { it.ports is Load.Ready } } }

        viewModel.side.ports.toggleDeclare(8080)
        viewModel.side.ports.setName(8080, "인쇄 미리보기")
        viewModel.side.ports.declare(8080)
        val declared = runBlocking {
            withTimeout(10.seconds) {
                ports.first { state ->
                    (state.ports as? Load.Ready)?.value?.any { it.run == "인쇄 미리보기" } == true
                }
            }
        }
        assertTrue(declared.names.isEmpty())
        val file = render("side-ports", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    /** 첫 실행에서 엔진 번들을 내려받는 중인 엔진. 웹 화면은 그리지 않는다. */
    private class DownloadingEngine : BrowserEngine {
        var prepared = false

        override val status = MutableStateFlow<BrowserStatus>(BrowserStatus.Downloading(42f))

        override fun prepare() {
            prepared = true
        }

        @Composable
        override fun Page(url: String, reload: Int, modifier: Modifier) = Unit
    }

    private companion object {
        const val RESUME = "2026-09-24-resume"
        const val SESSION_BUG = "2026-09-24-session-bug"

        const val FRAMES = 8
        const val FRAME_GAP_MS = 150L
    }
}
