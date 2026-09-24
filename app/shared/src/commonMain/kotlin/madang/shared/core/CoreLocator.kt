package madang.shared.core

import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import madang.api.model.Health

/** 앱 홈의 `core.port`를 읽는다. 파일이 없거나 숫자가 아니면 null. */
fun interface PortFileReader {
    fun readPort(): Int?
}

/** 주소 하나에 `GET /health`를 보낸다. 응답이 없으면 예외를 던진다. */
fun interface HealthProbe {
    suspend fun check(baseUrl: String): Health
}

/** core 프로세스를 띄운다. 띄우지 못하면 예외를 던진다. 모바일에는 없다. */
fun interface CoreLauncher {
    fun launch(): CoreProcess
}

/** 앱이 띄운 core 프로세스. */
interface CoreProcess {
    /** 실행 중이면 null, 끝났으면 종료 코드와 마지막 출력. */
    fun exitDetail(): String?

    fun stop()
}

/** 탐색이 지금 하는 일. 시작 화면에 보인다. */
sealed interface LocateStep {
    data class Probing(val baseUrl: String) : LocateStep

    data object Launching : LocateStep

    data object WaitingForStart : LocateStep
}

enum class FailureReason {
    /** 떠 있는 core가 없고 이 플랫폼은 core를 띄울 수 없다. */
    NOT_RUNNING,

    /** core 프로세스를 시작하지 못했다. */
    LAUNCH_FAILED,

    /** 띄운 core가 응답하기 전에 끝났다. */
    EXITED,

    /** 띄운 core가 제한 시간 안에 응답하지 않았다. */
    START_TIMEOUT
}

sealed interface LocateResult {
    data class Found(val baseUrl: String, val health: Health, val launched: Boolean) :
        LocateResult

    data class Failed(val reason: FailureReason, val tried: List<String>, val detail: String?) :
        LocateResult
}

/**
 * core를 찾고, 없으면 띄운다.
 *
 * 순서: 설정의 core 주소 → `core.port`의 포트 → 기본 주소. 모두 응답하지 않으면
 * [launcher]로 core를 띄우고 `core.port`가 생겨 `/health`가 응답할 때까지 기다린다.
 */
class CoreLocator(
    private val portFile: PortFileReader,
    private val probe: HealthProbe,
    private val launcher: CoreLauncher?,
    private val startTimeout: Duration = 20.seconds,
    private val pollInterval: Duration = 500.milliseconds
) {

    suspend fun locate(configuredUrl: String?, onStep: (LocateStep) -> Unit = {}): LocateResult {
        val candidates = candidateUrls(configuredUrl)
        for (url in candidates) {
            onStep(LocateStep.Probing(url))
            healthOrNull(url)?.let { return LocateResult.Found(url, it, launched = false) }
        }
        if (launcher == null) {
            return LocateResult.Failed(FailureReason.NOT_RUNNING, candidates, null)
        }
        onStep(LocateStep.Launching)
        val process = try {
            launcher.launch()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return LocateResult.Failed(FailureReason.LAUNCH_FAILED, candidates, e.message)
        }
        onStep(LocateStep.WaitingForStart)
        return waitForLaunched(process, candidates)
    }

    private suspend fun waitForLaunched(process: CoreProcess, tried: List<String>): LocateResult {
        val result = withTimeoutOrNull(startTimeout) { pollUntilReady(process, tried) }
        if (result != null) return result
        process.stop()
        return LocateResult.Failed(FailureReason.START_TIMEOUT, tried, "$startTimeout")
    }

    private suspend fun pollUntilReady(process: CoreProcess, tried: List<String>): LocateResult {
        while (true) {
            delay(pollInterval)
            process.exitDetail()?.let {
                return LocateResult.Failed(FailureReason.EXITED, tried, it)
            }
            val url = portFileUrl() ?: CoreClient.DEFAULT_BASE_URL
            healthOrNull(url)?.let { return LocateResult.Found(url, it, launched = true) }
        }
    }

    private fun candidateUrls(configuredUrl: String?): List<String> = listOfNotNull(
        configuredUrl?.trim()?.trimEnd('/')?.takeIf { it.isNotEmpty() },
        portFileUrl(),
        CoreClient.DEFAULT_BASE_URL
    ).distinct()

    private fun portFileUrl(): String? = portFile.readPort()?.let { "http://127.0.0.1:$it" }

    private suspend fun healthOrNull(url: String): Health? = try {
        probe.check(url)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }
}
