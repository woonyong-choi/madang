package madang.shared

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.job
import madang.api.model.HomeStatus
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
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
 * 화면 전환. 시작 → (전역 설정이 없으면 온보딩) → 메인 ↔ 설정.
 *
 * 연결 하나([CoreClient])를 온보딩·메인·설정이 함께 쓰고, 다시 연결하면 새로 만든다.
 */
class AppViewModel(private val deps: AppDependencies, private val scope: CoroutineScope) {

    private val _language = MutableStateFlow(deps.settings.load().language)
    val language: StateFlow<Language> = _language.asStateFlow()

    private var client: CoreClient? = null
    private var sessionScope: CoroutineScope = childScope()
    private var main: MainViewModel? = null

    /** 화면이 프로젝트 폴더를 고를 때 쓰는 플랫폼 대화상자. */
    val folderPicker: FolderPicker get() = deps.folderPicker

    /** 브라우저 탭이 쓰는 플랫폼 웹 엔진. */
    val browser: BrowserEngine get() = deps.browser

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
            onReconnect = ::reconnect,
            project = main?.state?.value?.targetProject
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

    private fun onConnected(core: CoreClient, home: HomeStatus) {
        client = core
        if (!home.initialized) {
            val onboarding =
                OnboardingViewModel(core, deps.claudeProbe, home.path, sessionScope, ::showMain)
            _screen.value = Screen.Onboarding(onboarding)
            onboarding.start()
        } else {
            showMain()
        }
    }

    private fun showMain() {
        val core = client ?: return
        val events = EventStream(deps.eventTransport(core))
        val newPageTitle = stringsFor(_language.value).navigator.untitledPage
        val viewModel = MainViewModel(
            core,
            events,
            sessionScope,
            newPageTitle,
            deps.settings,
            files = deps.localFiles
        )
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
