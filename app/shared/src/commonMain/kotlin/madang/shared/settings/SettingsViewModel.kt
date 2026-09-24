package madang.shared.settings

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.model.Issue
import madang.api.model.RoutesDocument
import madang.api.model.RunnerStatus
import madang.shared.core.CoreApiException
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow

/** routes.yaml 편집기 상태. */
sealed interface RoutesStatus {
    data object Loading : RoutesStatus

    data object Editing : RoutesStatus

    data object Saving : RoutesStatus

    data object Saved : RoutesStatus

    /** core 검사기가 거부했다. */
    data class Invalid(val issues: List<Issue>) : RoutesStatus

    data class Error(val message: String) : RoutesStatus
}

data class SettingsState(
    val coreUrl: String = "",
    val coreBinary: String = "",
    val connectedUrl: String = "",
    val language: Language = Language.KO,
    val routesText: String = "",
    val routesStatus: RoutesStatus = RoutesStatus.Loading,
    val runners: List<RunnerStatus> = emptyList(),
    val runnersError: String? = null
)

/**
 * 설정 화면. core 주소, routes.yaml, 실행기 목록, 언어.
 *
 * core 주소와 실행 파일 경로는 앱 설정에 저장하고 [onReconnect]로 다시 연결한다.
 * routes.yaml은 core에 보내 검사 결과를 받는다.
 */
class SettingsViewModel(
    private val core: CoreClient,
    private val store: AppSettingsStore,
    private val scope: CoroutineScope,
    private val onLanguageChange: (Language) -> Unit,
    private val onReconnect: () -> Unit
) {
    private val _state = MutableStateFlow(initialState())
    val state: StateFlow<SettingsState> = _state.asStateFlow()

    init {
        loadRoutes()
        refreshRunners()
    }

    fun setCoreUrl(url: String) = _state.update { it.copy(coreUrl = url) }

    fun setCoreBinary(path: String) = _state.update { it.copy(coreBinary = path) }

    /** 연결 설정을 저장하고 새 설정으로 core를 다시 찾는다. */
    fun applyConnection() {
        val current = _state.value
        store.save(
            store.load().copy(
                coreUrl = current.coreUrl.trim().ifEmpty { null },
                coreBinary = current.coreBinary.trim().ifEmpty { null }
            )
        )
        onReconnect()
    }

    fun setLanguage(language: Language) {
        store.save(store.load().copy(language = language))
        _state.update { it.copy(language = language) }
        onLanguageChange(language)
    }

    fun setRoutesText(text: String) = _state.update {
        it.copy(routesText = text, routesStatus = RoutesStatus.Editing)
    }

    fun saveRoutes() {
        val text = _state.value.routesText
        _state.update { it.copy(routesStatus = RoutesStatus.Saving) }
        scope.launch {
            val status = attempt {
                core.setup.saveRoutes(RoutesDocument(text)).bodyOrThrow()
                RoutesStatus.Saved
            }
            _state.update { it.copy(routesStatus = status) }
        }
    }

    fun loadRoutes() {
        _state.update { it.copy(routesStatus = RoutesStatus.Loading) }
        scope.launch {
            var text: String? = null
            val status = attempt {
                text = core.setup.getRoutes().bodyOrThrow().text
                RoutesStatus.Editing
            }
            _state.update { it.copy(routesText = text ?: it.routesText, routesStatus = status) }
        }
    }

    fun refreshRunners() {
        scope.launch {
            try {
                val runners = core.runners.listRunners().bodyOrThrow().runners
                _state.update { it.copy(runners = runners, runnersError = null) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(runnersError = e.message ?: "error") }
            }
        }
    }

    private fun initialState(): SettingsState {
        val settings = store.load()
        return SettingsState(
            coreUrl = settings.coreUrl.orEmpty(),
            coreBinary = settings.coreBinary.orEmpty(),
            connectedUrl = core.baseUrl,
            language = settings.language
        )
    }

    /** 검사 실패(400)는 [RoutesStatus.Invalid], 그 밖의 실패는 [RoutesStatus.Error]로 바꾼다. */
    private suspend fun attempt(block: suspend () -> RoutesStatus): RoutesStatus = try {
        block()
    } catch (e: CancellationException) {
        throw e
    } catch (e: CoreApiException) {
        if (e.status ==
            BAD_REQUEST
        ) {
            RoutesStatus.Invalid(e.issues)
        } else {
            RoutesStatus.Error(e.message.orEmpty())
        }
    } catch (e: Exception) {
        RoutesStatus.Error(e.message ?: "error")
    }
}

private const val BAD_REQUEST = 400
