package madang.shared.start

import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import madang.api.model.HomeStatus
import madang.shared.AppDependencies
import madang.shared.core.CoreClient
import madang.shared.core.CoreLocator
import madang.shared.core.FailureReason
import madang.shared.core.HealthProbe
import madang.shared.core.LocateResult
import madang.shared.core.LocateStep
import madang.shared.core.bodyOrThrow

sealed interface StartState {
    data class Locating(val step: LocateStep?) : StartState

    data class Failed(val reason: FailureReason?, val tried: List<String>, val detail: String?) :
        StartState

    data class Connected(val baseUrl: String, val version: String) : StartState
}

/**
 * 시작 화면. core를 찾거나 띄우고 앱 홈 상태를 받는다.
 *
 * 연결되면 [onConnected]로 클라이언트와 앱 홈 상태(`GET /home`)를 넘긴다.
 */
class StartViewModel(
    private val deps: AppDependencies,
    private val scope: CoroutineScope,
    private val onConnected: (CoreClient, HomeStatus) -> Unit
) {
    private val _state = MutableStateFlow<StartState>(StartState.Locating(null))
    val state: StateFlow<StartState> = _state.asStateFlow()

    private var job: Job? = null

    fun start() {
        if (job?.isActive == true) return
        _state.value = StartState.Locating(null)
        job = scope.launch { connect() }
    }

    fun retry() = start()

    /** 앱 설정에 저장된 core 주소. 없으면 빈 문자열. */
    fun configuredAddress(): String = deps.settings.load().coreUrl.orEmpty()

    /** core 주소를 앱 설정에 저장하고 다시 찾는다. 비우면 자동으로 찾는다. */
    fun retryWith(address: String) {
        val settings = deps.settings.load()
        deps.settings.save(settings.copy(coreUrl = address.trim().ifEmpty { null }))
        start()
    }

    private suspend fun connect() {
        val settings = deps.settings.load()
        val locator = CoreLocator(
            portFile = deps.portFile(settings),
            probe = HealthProbe { url ->
                deps.connect(url).use { withTimeout(PROBE_TIMEOUT) { it.health() } }
            },
            launcher = deps.launcher?.invoke(settings)
        )
        when (
            val result = locator.locate(settings.coreUrl) {
                _state.value = StartState.Locating(it)
            }
        ) {
            is LocateResult.Failed ->
                _state.value = StartState.Failed(result.reason, result.tried, result.detail)

            is LocateResult.Found -> openSession(result)
        }
    }

    private suspend fun openSession(found: LocateResult.Found) {
        val client = deps.connect(found.baseUrl)
        val home = try {
            client.setup.getHome().bodyOrThrow()
        } catch (e: CancellationException) {
            client.close()
            throw e
        } catch (e: Exception) {
            client.close()
            _state.value = StartState.Failed(null, listOf(found.baseUrl), e.message)
            return
        }
        _state.value = StartState.Connected(found.baseUrl, found.health.version)
        onConnected(client, home)
    }

    private companion object {
        val PROBE_TIMEOUT = 3.seconds
    }
}
