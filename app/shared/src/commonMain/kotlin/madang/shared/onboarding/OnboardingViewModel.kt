package madang.shared.onboarding

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.model.RunnerStatus
import madang.shared.core.CoreClient
import madang.shared.core.HomeInit
import madang.shared.core.bodyOrThrow
import madang.shared.settings.AppSettingsStore

enum class OnboardingStep { HOME, REMOTE, TOOLS, PERMISSIONS }

/** 도구 하나의 확인 결과. [status]가 null이면 아직 확인 중이다. */
data class ToolCheck(val name: String, val status: ToolStatus? = null)

data class OnboardingState(
    val step: OnboardingStep = OnboardingStep.HOME,
    val homePath: String = DEFAULT_HOME,
    val remote: String = "",
    val remoteInvalid: Boolean = false,
    val tools: List<ToolCheck> = AGENT_TOOLS.map { ToolCheck(it) },
    val runners: List<RunnerStatus> = emptyList(),
    val submitting: Boolean = false,
    val error: String? = null,
    val done: Boolean = false
) {
    val canGoNext: Boolean
        get() = when (step) {
            OnboardingStep.HOME -> homePath.isNotBlank()
            else -> !submitting
        }

    companion object {
        const val DEFAULT_HOME = "~/.madang"
        val AGENT_TOOLS = listOf("claude", "codex")
    }
}

/**
 * 첫 실행 온보딩. 앱 홈 위치 → 원격 저장소 → 도구 확인 → 권한 규칙 제안 순서로 간다.
 *
 * 앱은 앱 홈에 직접 쓰지 않는다. 마지막에 core에 앱 홈 초기화를 요청하고, 고른 경로는
 * 다음 실행에서 core를 찾을 수 있도록 앱 설정에만 남긴다. 권한 규칙은 제안만 한다.
 */
class OnboardingViewModel(
    private val core: CoreClient,
    private val toolProbe: ToolProbe,
    private val settings: AppSettingsStore,
    private val scope: CoroutineScope,
    private val onDone: () -> Unit
) {
    private val _state = MutableStateFlow(OnboardingState())
    val state: StateFlow<OnboardingState> = _state.asStateFlow()

    fun setHomePath(path: String) = _state.update { it.copy(homePath = path) }

    fun setRemote(remote: String) = _state.update {
        it.copy(remote = remote, remoteInvalid = false)
    }

    fun back() = _state.update { current ->
        val previous = OnboardingStep.entries.getOrNull(current.step.ordinal - 1)
        if (previous == null || current.submitting) current else current.copy(step = previous)
    }

    fun next() {
        val current = _state.value
        if (!current.canGoNext) return
        when (current.step) {
            OnboardingStep.HOME -> moveTo(OnboardingStep.REMOTE)
            OnboardingStep.REMOTE -> leaveRemote(current.remote)
            OnboardingStep.TOOLS -> moveTo(OnboardingStep.PERMISSIONS)
            OnboardingStep.PERMISSIONS -> finish()
        }
    }

    /** 권한 규칙 제안을 건너뛰고 앱 홈을 만든다. 규칙 파일은 바꾸지 않는다. */
    fun later() = finish()

    private fun leaveRemote(remote: String) {
        if (remote.isNotBlank() && !isRemoteAddress(remote.trim())) {
            _state.update { it.copy(remoteInvalid = true) }
            return
        }
        moveTo(OnboardingStep.TOOLS)
        checkTools()
    }

    private fun moveTo(step: OnboardingStep) = _state.update { it.copy(step = step, error = null) }

    private fun checkTools() {
        _state.update { state -> state.copy(tools = state.tools.map { ToolCheck(it.name) }) }
        for (tool in OnboardingState.AGENT_TOOLS) {
            scope.launch {
                val status = probeSafely(tool)
                _state.update { state ->
                    state.copy(
                        tools = state.tools.map {
                            if (it.name ==
                                tool
                            ) {
                                it.copy(status = status)
                            } else {
                                it
                            }
                        }
                    )
                }
            }
        }
        scope.launch {
            val runners = runCatching { core.runners.listRunners().bodyOrThrow().runners }
            _state.update { it.copy(runners = runners.getOrDefault(emptyList())) }
        }
    }

    private suspend fun probeSafely(tool: String): ToolStatus = try {
        toolProbe.probe(tool)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        ToolStatus(path = null, version = null, error = e.message)
    }

    private fun finish() {
        val current = _state.value
        if (current.submitting || current.done) return
        _state.update { it.copy(submitting = true, error = null) }
        scope.launch {
            val request = HomeInit(
                path = current.homePath.trim(),
                remote = current.remote.trim().ifEmpty { null }
            )
            try {
                core.setup.initHome(request)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(submitting = false, error = e.message ?: "error") }
                return@launch
            }
            rememberHome(request.path)
            _state.update { it.copy(submitting = false, done = true) }
            onDone()
        }
    }

    private fun rememberHome(path: String) {
        val homePath = path.takeUnless { it == OnboardingState.DEFAULT_HOME }
        settings.save(settings.load().copy(homePath = homePath))
    }
}

/** git 원격 주소 모양인지 본다: `https://`, `ssh://`, `git@host:path`. */
fun isRemoteAddress(text: String): Boolean = REMOTE_PATTERN.matches(text)

private val REMOTE_PATTERN = Regex("""^(https?://|ssh://|git@[^\s:]+:)\S+$""")
