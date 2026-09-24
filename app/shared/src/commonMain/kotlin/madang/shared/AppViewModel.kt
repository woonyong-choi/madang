package madang.shared

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.job
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.HomeStatus
import madang.shared.main.MainViewModel
import madang.shared.onboarding.OnboardingViewModel
import madang.shared.settings.Language
import madang.shared.settings.SettingsViewModel
import madang.shared.start.StartViewModel
import madang.shared.ui.stringsFor

/** 지금 보이는 화면. */
sealed interface Screen {
    data class Start(val viewModel: StartViewModel) : Screen

    data class Onboarding(val viewModel: OnboardingViewModel) : Screen

    data class Main(val viewModel: MainViewModel) : Screen

    data class Settings(val viewModel: SettingsViewModel) : Screen
}

/**
 * 화면 전환. 시작 → (앱 홈이 없으면 온보딩) → 메인 ↔ 설정.
 *
 * 연결 하나([CoreClient])를 온보딩·메인·설정이 함께 쓰고, 다시 연결하면 새로 만든다.
 */
class AppViewModel(private val deps: AppDependencies, private val scope: CoroutineScope) {

    private val _language = MutableStateFlow(deps.settings.load().language)
    val language: StateFlow<Language> = _language.asStateFlow()

    private var client: CoreClient? = null
    private var sessionScope: CoroutineScope = childScope()
    private var main: MainViewModel? = null

    private val _screen = MutableStateFlow<Screen>(newStart())
    val screen: StateFlow<Screen> = _screen.asStateFlow()

    fun start() = (screen.value as? Screen.Start)?.viewModel?.start()

    fun openSettings() {
        val core = client ?: return
        if (main == null) return
        val settings = SettingsViewModel(
            core = core,
            store = deps.settings,
            scope = sessionScope,
            onLanguageChange = { _language.value = it },
            onReconnect = ::reconnect
        )
        _screen.value = Screen.Settings(settings)
    }

    fun closeSettings() {
        main?.let { _screen.value = Screen.Main(it) }
    }

    /** 연결을 닫고 시작 화면부터 다시 찾는다. */
    fun reconnect() {
        closeSession()
        _screen.value = newStart().also { it.viewModel.start() }
    }

    private fun onConnected(core: CoreClient, home: HomeStatus?) {
        client = core
        if (home?.initialized == false) {
            _screen.value = Screen.Onboarding(
                OnboardingViewModel(core, deps.toolProbe, deps.settings, sessionScope, ::showMain)
            )
        } else {
            showMain()
        }
    }

    private fun showMain() {
        val core = client ?: return
        val events = EventStream(deps.eventTransport(core))
        val newPageTitle = stringsFor(_language.value).navigator.untitledPage
        val viewModel = MainViewModel(core, events, sessionScope, newPageTitle, deps.settings)
        main = viewModel
        _screen.value = Screen.Main(viewModel)
    }

    private fun newStart() = Screen.Start(StartViewModel(deps, sessionScope, ::onConnected))

    private fun closeSession() {
        sessionScope.cancel()
        client?.close()
        client = null
        main = null
        sessionScope = childScope()
    }

    private fun childScope() =
        CoroutineScope(scope.coroutineContext + SupervisorJob(scope.coroutineContext.job))
}
