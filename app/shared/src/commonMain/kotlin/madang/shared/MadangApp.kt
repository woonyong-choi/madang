package madang.shared

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import madang.shared.ui.LocalStrings
import madang.shared.ui.MainScreen
import madang.shared.ui.OnboardingScreen
import madang.shared.ui.SettingsScreen
import madang.shared.ui.StartScreen
import madang.shared.ui.stringsFor

/** 앱 루트. 시작 → 온보딩 → 메인 ↔ 설정. */
@Composable
fun MadangApp(viewModel: AppViewModel) {
    val screen by viewModel.screen.collectAsState()
    val language by viewModel.language.collectAsState()
    LaunchedEffect(viewModel) { viewModel.start() }
    CompositionLocalProvider(LocalStrings provides stringsFor(language)) {
        MaterialTheme {
            Surface(modifier = Modifier.fillMaxSize()) {
                when (val current = screen) {
                    is Screen.Start -> StartScreen(current.viewModel)

                    is Screen.Onboarding -> OnboardingScreen(current.viewModel)

                    is Screen.Main -> MainScreen(current.viewModel, viewModel::openSettings)

                    is Screen.Settings ->
                        SettingsScreen(current.viewModel, viewModel::closeSettings)
                }
            }
        }
    }
}
