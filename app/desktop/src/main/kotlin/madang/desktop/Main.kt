package madang.desktop

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.graphics.painter.BitmapPainter
import androidx.compose.ui.graphics.toComposeImageBitmap
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.io.File
import kotlinx.coroutines.delay
import madang.desktop.fake.ContractExamples
import madang.desktop.fake.FakeCore
import madang.shared.AppDependencies
import madang.shared.AppViewModel
import madang.shared.MadangApp
import madang.shared.core.CoreClient
import madang.shared.settings.InMemorySettingsStore
import org.jetbrains.skia.Image

/** MADANG_SMOKE=1이면 첫 프레임을 그린 3초 뒤 스스로 종료한다. */
private val smokeMode = System.getenv("MADANG_SMOKE") == "1"

/** MADANG_FAKE_CORE=1이면 계약 예시로 답하는 가짜 core에 붙는다. */
private val fakeCoreMode = System.getenv("MADANG_FAKE_CORE") == "1"

fun main() = application {
    val icon = remember { windowIcon() }
    val scope = rememberCoroutineScope()
    val app = remember { AppViewModel(dependencies(), scope) }
    Window(
        onCloseRequest = ::exitApplication,
        title = "Madang",
        icon = icon,
        state = rememberWindowState(size = DpSize(1280.dp, 800.dp))
    ) {
        MadangApp(app)

        if (smokeMode) {
            LaunchedEffect(Unit) {
                withFrameNanos { }
                println("madang: first frame rendered, exiting in 3s (MADANG_SMOKE=1)")
                delay(3_000)
                println("madang: screen at exit: ${app.screen.value::class.simpleName}")
                exitApplication()
            }
        }
    }
}

private fun dependencies(): AppDependencies {
    if (fakeCoreMode) return fakeDependencies()
    return AppDependencies(
        settings = FileSettingsStore(DesktopPaths.appConfigDir().resolve("settings.json")),
        toolProbe = CommandToolProbe(),
        portFile = { CorePortFile(DesktopPaths.appHome(it)) },
        launcher = { ProcessCoreLauncher(it) }
    )
}

/** 가짜 core는 떠 있는 core처럼 기본 주소에서 답한다. 앱 설정 파일은 건드리지 않는다. */
private fun fakeDependencies(): AppDependencies {
    val spec = File(System.getProperty("madang.openapiSpec") ?: "../core/openapi.yaml")
    val fake = FakeCore(
        ContractExamples.load(spec),
        homeReady = System.getenv("MADANG_FAKE_HOME") == "1"
    )
    println("madang: using fake core from ${spec.path}")
    return AppDependencies(
        settings = InMemorySettingsStore(),
        toolProbe = CommandToolProbe(),
        portFile = { { null } },
        launcher = null,
        connect = { CoreClient(it, fake.engine) },
        eventTransport = { fake.events }
    )
}

private fun windowIcon(): BitmapPainter {
    val bytes = checkNotNull(Thread.currentThread().contextClassLoader.getResource("icon.png"))
        .readBytes()
    return BitmapPainter(Image.makeFromEncoded(bytes).toComposeImageBitmap())
}
