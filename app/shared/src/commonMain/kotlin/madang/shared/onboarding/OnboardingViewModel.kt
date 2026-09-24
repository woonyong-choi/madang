package madang.shared.onboarding

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.ProjectsApi
import madang.api.model.ConfigDocument
import madang.api.model.HomeInit
import madang.api.model.ProjectCreate
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow

/** 온보딩 단계. 전역 설정 초기화 → 첫 프로젝트 폴더 → 도구 확인. */
enum class OnboardingStep { HOME, PROJECT, TOOLS }

/** 온보딩이 경로를 확인하는 도구. config.yaml `runners`의 러너 이름과 같다. */
const val CLAUDE_TOOL = "claude"
const val CODEX_TOOL = "codex"
val AGENT_TOOLS = listOf(CLAUDE_TOOL, CODEX_TOOL)

/**
 * 도구 하나의 확인 상태.
 *
 * @property path 로그인 셸이 찾았거나 사용자가 고른 절대 경로. 못 찾았으면 null.
 * @property input 사용자가 직접 넣는 경로.
 * @property checking 찾는 중이다.
 * @property rejected 사용자가 넣은 경로가 실행 파일이 아니었다.
 */
data class ToolState(
    val path: String? = null,
    val input: String = "",
    val checking: Boolean = false,
    val rejected: Boolean = false
) {
    val missing: Boolean get() = !checking && path == null
}

/**
 * 온보딩 상태.
 *
 * @property homePath core가 쓰는 앱 홈(전역 설정 폴더). 사용자가 고르지 않는다.
 * @property projectPath 첫 프로젝트로 등록할 폴더.
 * @property tools 도구 이름별 확인 상태([AGENT_TOOLS] 순서).
 * @property claude claude 확인 결과. 확인 중이면 null.
 * @property submitting core 요청 중이다.
 */
data class OnboardingState(
    val step: OnboardingStep = OnboardingStep.HOME,
    val homePath: String,
    val projectPath: String = "",
    val tools: Map<String, ToolState> = AGENT_TOOLS.associateWith { ToolState() },
    val claude: ClaudeStatus? = null,
    val submitting: Boolean = false,
    val error: String? = null,
    val done: Boolean = false
) {
    val canRegisterProject: Boolean
        get() = step == OnboardingStep.PROJECT && projectPath.isNotBlank() && !submitting

    fun tool(name: String): ToolState = tools[name] ?: ToolState()
}

/**
 * 첫 실행 온보딩.
 *
 * 앱은 앱 홈이나 프로젝트 폴더에 직접 쓰지 않는다. [start]가 core에 전역 설정 초기화
 * (`POST /home`)를 요청하고, 고른 폴더는 `POST /projects`로 등록한다. 마지막으로 도구 경로를
 * 확인한다. 로그인 셸이 찾은 경로(없으면 사용자가 고른 경로)를 전역 config.yaml
 * `runners.<도구>.bin`에 선언으로 저장(`PUT /config`)해 core 러너가 같은 파일을 쓰게 하고,
 * 그 claude로 설치·로그인 상태를 본다. 로그인하지 않았어도 시작할 수 있다.
 *
 * @param homePath core가 알려 준 앱 홈 경로(`GET /home`).
 */
class OnboardingViewModel(
    private val core: CoreClient,
    private val claudeProbe: ClaudeProbe,
    private val toolLocator: ToolLocator,
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

    /** 고른 폴더를 프로젝트로 등록하고 도구 확인으로 넘어간다. */
    fun registerProject() {
        val current = _state.value
        if (!current.canRegisterProject) return
        submit {
            projectsApi.createProject(ProjectCreate(path = current.projectPath.trim()))
                .bodyOrThrow()
            _state.update { it.copy(step = OnboardingStep.TOOLS) }
            checkTools()
        }
    }

    /** 로그인 셸로 도구를 다시 찾고, 찾은 경로를 저장한 뒤 claude 상태를 본다. */
    fun checkTools() {
        _state.update { state ->
            state.copy(
                tools = state.tools.mapValues { (_, tool) ->
                    tool.copy(path = null, checking = true, rejected = false)
                },
                claude = null,
                error = null
            )
        }
        scope.launch {
            val found = AGENT_TOOLS.associateWith { locate(it) }
            _state.update { state ->
                state.copy(
                    tools = state.tools.mapValues { (name, tool) ->
                        tool.copy(path = found[name], checking = false)
                    }
                )
            }
            saveBins(found.mapNotNull { (tool, path) -> path?.let { tool to it } }.toMap())
            checkClaude()
        }
    }

    fun setToolInput(tool: String, path: String) = updateTool(tool) {
        it.copy(input = path, rejected = false)
    }

    /** 사용자가 넣은 경로가 실행 파일이면 그 도구의 경로로 저장한다. */
    fun useToolInput(tool: String) {
        val path = _state.value.tool(tool).input.trim()
        if (path.isEmpty()) return
        scope.launch {
            if (!isExecutable(path)) {
                updateTool(tool) { it.copy(rejected = true) }
                return@launch
            }
            updateTool(tool) { it.copy(path = path, rejected = false) }
            saveBins(mapOf(tool to path))
            if (tool == CLAUDE_TOOL) checkClaude()
        }
    }

    fun finish() {
        val current = _state.value
        if (current.step != OnboardingStep.TOOLS || current.done) return
        _state.update { it.copy(done = true) }
        onDone()
    }

    private suspend fun checkClaude() {
        _state.update { it.copy(claude = null) }
        val bin = _state.value.tool(CLAUDE_TOOL).path
        val status = if (bin == null) {
            ClaudeStatus(installed = false, loggedIn = false)
        } else {
            try {
                claudeProbe.check(bin)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                ClaudeStatus(installed = false, loggedIn = false, error = e.message)
            }
        }
        _state.update { it.copy(claude = status) }
    }

    /** config.yaml 원문을 받아 `runners.<도구>.bin`만 고쳐 다시 저장한다. 검사는 core가 한다. */
    private suspend fun saveBins(bins: Map<String, String>) {
        if (bins.isEmpty()) return
        try {
            val current = core.setup.getConfig().bodyOrThrow().text
            val updated = bins.entries.fold(current) { text, (tool, bin) ->
                withRunnerBin(text, tool, bin)
            }
            core.setup.saveConfig(ConfigDocument(updated)).bodyOrThrow()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            _state.update { it.copy(error = e.message ?: "error") }
        }
    }

    private suspend fun locate(tool: String): String? = try {
        toolLocator.locate(tool)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    private suspend fun isExecutable(path: String): Boolean = try {
        toolLocator.isExecutable(path)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        false
    }

    private fun updateTool(name: String, change: (ToolState) -> ToolState) = _state.update {
        it.copy(tools = it.tools + (name to change(it.tool(name))))
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
