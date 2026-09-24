package madang.shared.main

import kotlin.time.Duration
import madang.api.model.Issue
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.Project
import madang.api.model.RunStreamEvent

/** 이벤트 연결 상태. */
sealed interface EventLink {
    data object Connecting : EventLink

    data object Live : EventLink

    data class Retrying(val cause: String?, val retryIn: Duration) : EventLink
}

/**
 * 보냈지만 core의 페이지에 아직 없는 사용자 메시지(낙관적 추가).
 *
 * @property localId 앱이 붙인 임시 key.
 * @property messageId core가 저장한 메시지 블록 id. 응답을 받기 전에는 null.
 */
data class PendingMessage(val localId: String, val text: String, val messageId: String? = null)

/** 탭이 따로 받아 오는 내용의 상태. */
sealed interface Load<out T> {
    data object Loading : Load<Nothing>

    data class Ready<T>(val value: T) : Load<T>

    data class Failed(val message: String?) : Load<Nothing>
}

/**
 * 디프 탭 내용.
 *
 * @property repository 작업 폴더가 git 저장소다. 아니면 [files]는 비어 있다.
 */
data class DiffView(val repository: Boolean, val files: List<DiffFile>)

/**
 * 데이터 탭에서 고치는 블록 원문. 저장은 core가 검사한다.
 *
 * @property issues 마지막 저장에서 core가 거부한 이유.
 */
data class DataDraft(
    val text: String,
    val saving: Boolean = false,
    val issues: List<Issue> = emptyList(),
    val error: String? = null
) {
    val issuesByLine: Map<Int, List<Issue>>
        get() = issues.filter { it.line != null }.groupBy { checkNotNull(it.line) }
}

/**
 * 3열에 열린 페이지.
 *
 * @property contents 블록 탭으로 여는 블록(doc·data·view) id별 파일 내용.
 * @property runEvents run 탭에서 읽은 run 번호별 이벤트 로그.
 * @property pending 낙관적으로 붙인 메시지. core 페이지에 같은 블록이 생기면 빠진다.
 * @property answered 답을 보낸 사람 결정 id. flow가 다시 돌거나 새 질문이 오면 지운다.
 * @property files 파일 탭의 절대 경로별 내용.
 * @property diff 디프 탭 내용. 디프 탭을 연 적이 없으면 null.
 * @property drafts 데이터 탭에서 고치는 중인 블록 id별 원문.
 */
data class OpenPage(
    val detail: PageDetail,
    val contents: Map<String, String> = emptyMap(),
    val runEvents: Map<Int, List<RunStreamEvent>> = emptyMap(),
    val pending: List<PendingMessage> = emptyList(),
    val answered: String? = null,
    val files: Map<String, Load<String>> = emptyMap(),
    val diff: Load<DiffView>? = null,
    val drafts: Map<String, DataDraft> = emptyMap()
) {
    /** 블록 흐름 끝에 아직 core에 없는 메시지를 붙인 것. */
    val flowItems: List<FlowItem>
        get() = pageFlow(detail) + unconfirmed().map { FlowItem.Pending(it) }

    /** 새로 받은 페이지로 바꾼다. 페이지에 들어온 메시지는 낙관적 목록에서 뺀다. */
    fun withDetail(next: PageDetail): OpenPage = copy(detail = next).pruned()

    /** core가 메시지를 받았다. 이벤트로 이미 페이지에 들어왔으면 바로 뺀다. */
    fun withAccepted(localId: String, messageId: String): OpenPage = copy(
        pending = pending.map { if (it.localId == localId) it.copy(messageId = messageId) else it }
    ).pruned()

    private fun unconfirmed(): List<PendingMessage> {
        val ids = detail.blocks.mapTo(mutableSetOf()) { it.id }
        return pending.filter { it.messageId == null || it.messageId !in ids }
    }

    private fun pruned(): OpenPage = copy(pending = unconfirmed())
}

/**
 * 메인 화면 상태(3열과 가운데 열의 탭).
 *
 * @property source 1열에서 고른 프로젝트 또는 태그. 2열이 이것을 보여 준다.
 * @property focusProject 프로젝트 포커스. 있으면 1열에 그 프로젝트와 하위만 보인다.
 * @property selectedPage 2열에서 고른 페이지. [page]는 그 페이지를 불러온 결과다.
 * @property pane 키보드 포커스가 있는 열.
 * @property tabs 열린 페이지의 가운데 열 탭 세트.
 * @property toggled 접힘 규칙과 반대로 둔 본문 항목의 key.
 * @property activeRuns 페이지 id별 진행 중인 run.
 * @property unknownFilesOpen 열린 페이지의 미등록 파일 목록을 펼쳤다.
 */
data class MainState(
    val baseUrl: String,
    val link: EventLink = EventLink.Connecting,
    val loadError: String? = null,
    val loaded: Boolean = false,
    val projects: List<Project> = emptyList(),
    val cards: List<PageCard> = emptyList(),
    val source: ListSource? = null,
    val expandedProjects: Set<String> = emptySet(),
    val expandedTags: Set<String> = emptySet(),
    val focusProject: String? = null,
    val filter: PageFilter = PageFilter(),
    val selectedPage: String? = null,
    val page: OpenPage? = null,
    val tabs: TabSet = TabSet(),
    val pane: Pane = Pane.PROJECTS,
    val expandAll: Boolean = false,
    val toggled: Set<String> = emptySet(),
    val activeRuns: Map<String, ActiveRun> = emptyMap(),
    val unknownFilesOpen: Boolean = false,
    val sidebar: Sidebar = Sidebar()
) {
    val projectRows: List<ProjectRow> get() = projectRows(projects, expandedProjects, focusProject)

    val tagRows: List<TagRow> get() = tagRows(cards, expandedTags)

    val listCards: List<PageCard> get() = visibleCards(cards, projects, source, filter)

    /** 입력창이 보낼 곳. 활성 탭을 따른다. */
    val sendTarget: SendTarget? get() = page?.let { sendTarget(it.detail, tabs) }

    /** 1열에서 위아래로 오가는 순서. 프로젝트 다음에 태그. */
    val navItems: List<ListSource>
        get() = projectRows.map { ListSource.InProject(it.project.id) } +
            tagRows.map { ListSource.WithTag(it.path) }

    /**
     * 새 페이지가 들어갈 프로젝트. 고른 프로젝트, 없으면 열린 페이지의 프로젝트, 없으면 첫
     * 프로젝트. 등록한 프로젝트가 없으면 null.
     */
    val targetProject: String?
        get() = (source as? ListSource.InProject)?.id
            ?: page?.detail?.project
            ?: projectRows.firstOrNull()?.project?.id

    /**
     * 목록을 새로 받았을 때 고른 프로젝트·태그와 펼침을 맞춘다. 처음이면 하위가 있는 프로젝트를
     * 펼친다.
     */
    fun withLoaded(projects: List<Project>, cards: List<PageCard>): MainState {
        val next = copy(projects = projects, cards = cards, loadError = null, loaded = true)
        val expanded = if (loaded) {
            expandedProjects
        } else {
            projects.mapNotNullTo(mutableSetOf()) { it.parent }
        }
        val keep = source?.takeIf { it in next.copy(expandedProjects = expanded).navItems }
        val fallback = next.copy(expandedProjects = expanded).projectRows.firstOrNull()?.project
        return next.copy(
            expandedProjects = expanded,
            source = keep ?: fallback?.let { ListSource.InProject(it.id) },
            focusProject = focusProject?.takeIf { id -> projects.any { it.id == id } }
        )
    }
}
