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
import kotlin.test.assertTrue
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
 * 넓은 창(3열), 좁은 창(목록 + 본문 2열), 더 좁은 창(본문 1열)을 그린다. 결과는
 * `madang.screenshotDir`(기본 `build/screenshots`)에 쓴다.
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

    private fun viewModel(): MainViewModel {
        val spec = File(checkNotNull(System.getProperty("madang.openapiSpec")))
        val home = File(checkNotNull(javaClass.getResource("/fixture-home")).toURI())
        val fake =
            FakeCore(ContractExamples.load(spec), homeReady = true, fixture = FixtureHome(home))
        val core = CoreClient(CoreClient.DEFAULT_BASE_URL, fake.engine)
        return MainViewModel(core, EventStream(fake.events), scope, "제목 없음")
    }

    private fun MainViewModel.await(condition: (MainState) -> Boolean): MainState = runBlocking {
        withTimeout(10.seconds) { state.first(condition) }
    }

    private fun MainViewModel.show(space: String, page: String, pane: Pane) {
        select(ListSource.InSpace(space))
        openPage(page)
        await { it.page?.detail?.id == page && it.page?.contents?.size == docAndDataCount(it) }
        focusPane(pane)
    }

    private fun docAndDataCount(state: MainState): Int =
        state.page?.detail?.blocks?.count { it.type.value == "doc" || it.type.value == "data" } ?: 0

    private fun render(name: String, widthDp: Int, heightDp: Int, viewModel: MainViewModel): File {
        val density = 2f
        val scene = ImageComposeScene(
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
        try {
            var frame = scene.render(0)
            for (i in 1..FRAMES) {
                Thread.sleep(FRAME_GAP_MS)
                frame = scene.render(i * FRAME_GAP_MS * 1_000_000)
            }
            val png = checkNotNull(frame.encodeToData(EncodedImageFormat.PNG)).bytes
            outDir.mkdirs()
            return File(outDir, "$name.png").apply { writeBytes(png) }
        } finally {
            scene.close()
        }
    }

    @Test
    fun rendersWideNarrowAndSinglePageLayouts() {
        val viewModel = viewModel()
        val loaded = viewModel.await { it.loaded && it.activeRuns.isNotEmpty() }
        assertEquals(5, loaded.spaces.size)
        assertEquals(9, loaded.cards.size)

        viewModel.show("jobs", "2026-09-24-resume", Pane.LIST)
        val wide = render("wide", 1440, 900, viewModel)

        viewModel.show("jobs-2026", "2026-09-20-cover-letter", Pane.PAGE)
        val narrow = render("narrow", 960, 760, viewModel)

        viewModel.show("auth-svc", "2026-09-24-session-bug", Pane.PAGE)
        val page = render("page", 620, 1000, viewModel)

        for (file in listOf(wide, narrow, page)) assertTrue(file.length() > 10_000, file.path)
    }

    private companion object {
        const val FRAMES = 8
        const val FRAME_GAP_MS = 150L
    }
}
