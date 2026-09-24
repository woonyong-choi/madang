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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import madang.desktop.fake.ContractExamples
import madang.desktop.fake.FakeCore
import madang.desktop.fake.FixtureHome
import madang.shared.core.CoreClient
import madang.shared.settings.DocumentStatus
import madang.shared.settings.InMemorySettingsStore
import madang.shared.settings.SettingsDocument
import madang.shared.settings.SettingsState
import madang.shared.settings.SettingsViewModel
import madang.shared.ui.KoreanStrings
import madang.shared.ui.LocalStrings
import madang.shared.ui.SettingsScreen
import org.jetbrains.skia.EncodedImageFormat

/**
 * 설정 화면을 픽스처 가짜 core로 화면 밖에서 그린다. 프로젝트 설정에 모르는 키를 넣어 저장이
 * 거부된 모습(`settings-config.png`)을 남긴다.
 */
class SettingsScreenshotTest {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val outDir = File(System.getProperty("madang.screenshotDir") ?: "build/screenshots")

    @AfterTest
    fun tearDown() = scope.cancel()

    @Test
    fun rejectedProjectConfigIsShownOnItsLine() {
        val spec = File(checkNotNull(System.getProperty("madang.openapiSpec")))
        val home = File(checkNotNull(javaClass.getResource("/fixture-home")).toURI())
        val fake = FakeCore(ContractExamples.load(spec), homeReady = true, FixtureHome(home))
        val core = CoreClient(CoreClient.DEFAULT_BASE_URL, fake.engine)
        val viewModel =
            SettingsViewModel(core, InMemorySettingsStore(), scope, {}, {}, project = "jobs")
        val loaded = await(viewModel) {
            it.document(SettingsDocument.PROJECT_CONFIG).status == DocumentStatus.Editing
        }
        assertEquals("jobs", loaded.project)

        viewModel.setText(SettingsDocument.PROJECT_CONFIG, "track: true\nrun: []\n")
        viewModel.save(SettingsDocument.PROJECT_CONFIG)
        val rejected = await(viewModel) {
            it.document(SettingsDocument.PROJECT_CONFIG).status is DocumentStatus.Invalid
        }
        assertEquals(setOf(2), rejected.document(SettingsDocument.PROJECT_CONFIG).issuesByLine.keys)

        val file = render(viewModel)
        assertTrue(file.length() > 10_000, file.path)
    }

    private fun await(viewModel: SettingsViewModel, condition: (SettingsState) -> Boolean) =
        runBlocking { withTimeout(10.seconds) { viewModel.state.first(condition) } }

    private fun render(viewModel: SettingsViewModel): File {
        val density = 2f
        val scene = ImageComposeScene(
            width = (1100 * density).toInt(),
            height = (1400 * density).toInt(),
            density = Density(density)
        ) {
            CompositionLocalProvider(LocalStrings provides KoreanStrings) {
                MaterialTheme { Surface { SettingsScreen(viewModel) {} } }
            }
        }
        try {
            var image = scene.render(0)
            repeat(FRAMES) { frame ->
                Thread.sleep(FRAME_GAP_MS)
                image = scene.render((frame + 1) * FRAME_GAP_MS * 1_000_000)
            }
            outDir.mkdirs()
            val png = checkNotNull(image.encodeToData(EncodedImageFormat.PNG)).bytes
            return File(outDir, "settings-config.png").apply { writeBytes(png) }
        } finally {
            scene.close()
        }
    }

    private companion object {
        const val FRAMES = 6
        const val FRAME_GAP_MS = 150L
    }
}
