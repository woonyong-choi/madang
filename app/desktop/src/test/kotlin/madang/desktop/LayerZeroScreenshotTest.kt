package madang.desktop

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.ImageComposeScene
import androidx.compose.ui.unit.Density
import java.io.File
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.datetime.TimeZone
import madang.desktop.fake.ContractExamples
import madang.desktop.fake.FakeCore
import madang.desktop.fake.FixtureHome
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.main.BlockTab
import madang.shared.main.FlowItem
import madang.shared.main.ListSource
import madang.shared.main.MainState
import madang.shared.main.MainViewModel
import madang.shared.main.Pane
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
 * 미등록 파일 띠·사람 결정 카드·메모리 검사 오류가 보이는 화면, 가운데 열의 페이지 탭과 run 탭을
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
        state.page?.detail?.blocks?.count { it.type.value == "doc" || it.type.value == "data" } ?: 0

    /** 화면 밖 장면 하나. 프레임을 흘려 보내고 지금 화면을 PNG로 남긴다. */
    private inner class OffscreenMain(widthDp: Int, heightDp: Int, viewModel: MainViewModel) :
        AutoCloseable {
        private val density = 2f
        private val scene = ImageComposeScene(
            width = (widthDp * density).toInt(),
            height = (heightDp * density).toInt(),
            density = Density(density)
        ) {
            CompositionLocalProvider(
                LocalStrings provides KoreanStrings,
                LocalListClock provides clock
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

    private fun render(name: String, widthDp: Int, heightDp: Int, viewModel: MainViewModel): File =
        OffscreenMain(widthDp, heightDp, viewModel).use {
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

        viewModel.toggleMemory()
        val memory = viewModel.memory.state
        runBlocking { withTimeout(10.seconds) { memory.first { it.current != null } } }
        val broken = checkNotNull(memory.value.current).text
            .replace("status: review", "status: finished")
        viewModel.memory.edit(broken)
        viewModel.memory.save()
        val rejected = runBlocking {
            withTimeout(10.seconds) { memory.first { it.current?.issues?.isNotEmpty() == true } }
        }
        assertEquals(setOf(2), checkNotNull(rejected.current).issuesByLine.keys)

        val file = render("decision-memory", 1440, 900, viewModel)
        assertTrue(file.length() > 10_000, file.path)
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
        assertEquals(listOf(BlockTab.Block("b05"), BlockTab.Run(2)), withEvents.tabs.tabs)
        assertEquals(BlockTab.Run(2), withEvents.tabs.active)
        val run = render("tabs-run", 1440, 900, viewModel)

        for (file in listOf(page, run)) assertTrue(file.length() > 10_000, file.path)
    }

    private companion object {
        const val RESUME = "2026-09-24-resume"

        const val FRAMES = 8
        const val FRAME_GAP_MS = 150L
    }
}
