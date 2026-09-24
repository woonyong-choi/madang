package madang.shared.onboarding

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.ProjectsApi
import madang.api.model.HomeInit
import madang.api.model.ProjectCreate
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow

/** 온보딩 단계. 전역 설정 초기화 → 첫 프로젝트 폴더 → claude 확인. */
enum class OnboardingStep { HOME, PROJECT, CLAUDE }

/**
 * 온보딩 상태.
 *
 * @property homePath core가 쓰는 앱 홈(전역 설정 폴더). 사용자가 고르지 않는다.
 * @property projectPath 첫 프로젝트로 등록할 폴더.
 * @property claude claude 확인 결과. 확인 중이면 null.
 * @property submitting core 요청 중이다.
 */
data class OnboardingState(
    val step: OnboardingStep = OnboardingStep.HOME,
    val homePath: String,
    val projectPath: String = "",
    val claude: ClaudeStatus? = null,
    val submitting: Boolean = false,
    val error: String? = null,
    val done: Boolean = false
) {
    val canRegisterProject: Boolean
        get() = step == OnboardingStep.PROJECT && projectPath.isNotBlank() && !submitting
}

/**
 * 첫 실행 온보딩.
 *
 * 앱은 앱 홈이나 프로젝트 폴더에 직접 쓰지 않는다. [start]가 core에 전역 설정 초기화
 * (`POST /home`)를 요청하고, 고른 폴더는 `POST /projects`로 등록한다. 마지막으로 claude의
 * 설치·로그인 상태를 보여 준다. 로그인하지 않았어도 시작할 수 있다.
 *
 * @param homePath core가 알려 준 앱 홈 경로(`GET /home`).
 */
class OnboardingViewModel(
    private val core: CoreClient,
    private val claudeProbe: ClaudeProbe,
    homePath: String,
    private val scope: CoroutineScope,
    private val onDone: () -> Unit
) {
    private val _state = MutableStateFlow(OnboardingState(homePath = homePath))
    val state: StateFlow<OnboardingState> = _state.asStateFlow()

    private val projectsApi = core.api(::ProjectsApi)

    /** 전역 설정을 만든다. 실패하면 오류를 보이고 다시 부를 수 있다. */
    fun start() {
        val current = _state.value
        if (current.step != OnboardingStep.HOME || current.submitting) return
        submit {
            core.setup.initHome(HomeInit(path = current.homePath)).bodyOrThrow()
            _state.update { it.copy(step = OnboardingStep.PROJECT) }
        }
    }

    fun setProjectPath(path: String) = _state.update { it.copy(projectPath = path, error = null) }

    /** 고른 폴더를 프로젝트로 등록하고 claude 확인으로 넘어간다. */
    fun registerProject() {
        val current = _state.value
        if (!current.canRegisterProject) return
        submit {
            projectsApi.createProject(ProjectCreate(path = current.projectPath.trim()))
                .bodyOrThrow()
            _state.update { it.copy(step = OnboardingStep.CLAUDE) }
            checkClaude()
        }
    }

    /** claude 상태를 다시 본다. */
    fun checkClaude() {
        _state.update { it.copy(claude = null) }
        scope.launch {
            val status = try {
                claudeProbe.check()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                ClaudeStatus(installed = false, loggedIn = false, error = e.message)
            }
            _state.update { it.copy(claude = status) }
        }
    }

    fun finish() {
        val current = _state.value
        if (current.step != OnboardingStep.CLAUDE || current.done) return
        _state.update { it.copy(done = true) }
        onDone()
    }

    private fun submit(block: suspend () -> Unit) {
        _state.update { it.copy(submitting = true, error = null) }
        scope.launch {
            try {
                block()
                _state.update { it.copy(submitting = false) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(submitting = false, error = e.message ?: "error") }
            }
        }
    }
}
