package madang.desktop

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import kotlinx.coroutines.delay
import madang.shared.MadangApp

/** MADANG_SMOKE=1이면 첫 프레임을 그린 3초 뒤 스스로 종료한다. */
private val smokeMode = System.getenv("MADANG_SMOKE") == "1"

fun main() = application {
    Window(
        onCloseRequest = ::exitApplication,
        title = "Madang",
        icon = painterResource("icon.png"),
        state = rememberWindowState(size = DpSize(1280.dp, 800.dp))
    ) {
        MadangApp()

        if (smokeMode) {
            LaunchedEffect(Unit) {
                withFrameNanos { }
                println("madang: first frame rendered, exiting in 3s (MADANG_SMOKE=1)")
                delay(3_000)
                exitApplication()
            }
        }
    }
}
