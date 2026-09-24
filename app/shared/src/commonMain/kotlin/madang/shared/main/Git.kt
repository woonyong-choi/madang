package madang.shared.main

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.GitApi
import madang.api.model.GitBranches
import madang.api.model.GitCommitCreate
import madang.api.model.GitFile
import madang.api.model.GitLogEntry
import madang.api.model.GitStage
import madang.api.model.GitStatus
import madang.api.model.GitWorktree
import madang.shared.core.bodyOrThrow

/** git 탭 로그에 보이는 커밋 수. */
const val GIT_LOG_LIMIT = 20

/** 인덱스에 들어간 변경이 있다(`git status --porcelain`의 첫 글자). */
val GitFile.staged: Boolean get() = code.first() != ' ' && code != UNTRACKED

/** 작업 트리에 스테이징하지 않은 변경이 있다(둘째 글자, 추적 안 된 파일 포함). */
val GitFile.unstaged: Boolean get() = code.getOrElse(1) { ' ' } != ' ' || code == UNTRACKED

private const val UNTRACKED = "??"

/**
 * git 탭이 보이는 것. 저장소가 아니면 [status]만 있고 나머지는 비어 있다.
 *
 * @property branches 로컬 브랜치와 메인 체크아웃의 브랜치.
 * @property worktrees 메인 체크아웃과 워크트리, 그 워크트리를 쓰는 페이지.
 * @property log HEAD에서 거슬러 올라간 최근 커밋.
 */
data class GitView(
    val status: GitStatus,
    val branches: GitBranches? = null,
    val worktrees: List<GitWorktree> = emptyList(),
    val log: List<GitLogEntry> = emptyList()
) {
    val repository: Boolean get() = status.repository
}

/**
 * git 탭 상태. [project]가 null이면 닫혀 있다.
 *
 * @property page 열린 페이지. 있으면 그 페이지의 워크트리가 대상이다.
 * @property message 커밋 메시지 입력.
 * @property busy core에 보낸 조작이 끝나지 않았다.
 * @property error 마지막 조작을 core가 거부한 이유(정책 `denied`, 원격 없음 등).
 */
data class GitState(
    val project: String? = null,
    val page: String? = null,
    val view: Load<GitView>? = null,
    val message: String = "",
    val busy: Boolean = false,
    val error: String? = null
)

/**
 * git 탭. 상태·브랜치·워크트리·로그를 core에서 받고, 스테이지·커밋·푸시·풀·git 시작을 core에
 * 요청한다. 앱은 git을 직접 실행하지 않는다. 저장소가 아니면 상태만 받고 "git 시작"만 보인다.
 */
class GitViewModel(private val api: GitApi, private val scope: CoroutineScope) {

    private val _state = MutableStateFlow(GitState())
    val state: StateFlow<GitState> = _state.asStateFlow()

    fun open(project: String, page: String?) {
        val current = _state.value
        if (current.project == project && current.page == page) return
        _state.value = GitState(project = project, page = page)
        reload()
    }

    fun close() {
        _state.value = GitState()
    }

    fun setMessage(message: String) = _state.update { it.copy(message = message) }

    /** 다시 받는다. 받는 동안 앞의 내용을 그대로 보인다. */
    fun reload() {
        val (project, page) = target() ?: return
        _state.update { it.copy(view = it.view.takeIf { v -> v is Load.Ready } ?: Load.Loading) }
        scope.launch {
            val view = loadOf { fetch(project, page) }
            _state.update {
                if (it.project == project &&
                    it.page == page
                ) {
                    it.copy(view = view)
                } else {
                    it
                }
            }
        }
    }

    /** [paths]를 스테이징한다. null이면 모든 변경. */
    fun stage(paths: List<String>?) = act { project, page ->
        api.stageGit(project, GitStage(paths), page).bodyOrThrow()
    }

    /** 스테이징한 변경을 입력한 메시지로 커밋한다. 메시지가 비었으면 보내지 않는다. */
    fun commit() {
        val message = _state.value.message.trim()
        if (message.isEmpty()) return
        act { project, page ->
            api.commitGit(project, GitCommitCreate(message), page).bodyOrThrow()
            _state.update { if (it.message.trim() == message) it.copy(message = "") else it }
        }
    }

    fun push() = act { project, page -> api.pushGit(project, page).bodyOrThrow() }

    fun pull() = act { project, page -> api.pullGit(project, page).bodyOrThrow() }

    /** 프로젝트 폴더를 git 저장소로 만든다("git 시작"). */
    fun init() = act { project, _ -> api.initGit(project).bodyOrThrow() }

    /** `git.changed`. 보고 있는 프로젝트면 다시 받는다. */
    fun onChanged(project: String) {
        if (_state.value.project == project) reload()
    }

    private suspend fun fetch(project: String, page: String?): GitView {
        val status = api.getGitStatus(project, page).bodyOrThrow()
        if (!status.repository) return GitView(status)
        return GitView(
            status = status,
            branches = api.listGitBranches(project).bodyOrThrow(),
            worktrees = api.listGitWorktrees(project).bodyOrThrow(),
            log = api.getGitLog(project, page, limit = GIT_LOG_LIMIT).bodyOrThrow()
        )
    }

    /** core에 조작 하나를 보내고 끝나면 다시 받는다. 거부되면 이유를 보인다. */
    private fun act(block: suspend (project: String, page: String?) -> Unit) {
        val (project, page) = target() ?: return
        if (_state.value.busy) return
        _state.update { it.copy(busy = true, error = null) }
        scope.launch {
            val done = loadOf { block(project, page) }
            _state.update {
                if (it.project != project) return@update it
                it.copy(busy = false, error = (done as? Load.Failed)?.message)
            }
            reload()
        }
    }

    private fun target(): Pair<String, String?>? =
        _state.value.project?.let { it to _state.value.page }
}
