package madang.shared.main

import kotlin.time.Duration
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.Space

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

/**
 * 3열에 열린 페이지.
 *
 * @property contents doc·data 블록 id별 파일 내용.
 * @property pending 낙관적으로 붙인 메시지. core 페이지에 같은 블록이 생기면 빠진다.
 * @property answered 답을 보낸 사람 결정 id. flow가 다시 돌거나 새 질문이 오면 지운다.
 */
data class OpenPage(
    val detail: PageDetail,
    val contents: Map<String, String> = emptyMap(),
    val pending: List<PendingMessage> = emptyList(),
    val answered: String? = null
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
 * 레이어 0 상태.
 *
 * @property source 1열에서 고른 공간 또는 태그. 2열이 이것을 보여 준다.
 * @property focusSpace 공간 포커스. 있으면 1열에 그 공간과 하위만 보인다.
 * @property selectedPage 2열에서 고른 페이지. [page]는 그 페이지를 불러온 결과다.
 * @property pane 키보드 포커스가 있는 열.
 * @property toggled 접힘 규칙과 반대로 둔 본문 항목의 key.
 * @property activeRuns 페이지 id별 진행 중인 run.
 * @property unknownFilesOpen 열린 페이지의 미등록 파일 목록을 펼쳤다.
 */
data class MainState(
    val baseUrl: String,
    val link: EventLink = EventLink.Connecting,
    val loadError: String? = null,
    val loaded: Boolean = false,
    val spaces: List<Space> = emptyList(),
    val cards: List<PageCard> = emptyList(),
    val source: ListSource? = null,
    val expandedSpaces: Set<String> = emptySet(),
    val expandedTags: Set<String> = emptySet(),
    val focusSpace: String? = null,
    val filter: PageFilter = PageFilter(),
    val selectedPage: String? = null,
    val page: OpenPage? = null,
    val pane: Pane = Pane.SPACES,
    val expandAll: Boolean = false,
    val toggled: Set<String> = emptySet(),
    val activeRuns: Map<String, ActiveRun> = emptyMap(),
    val unknownFilesOpen: Boolean = false
) {
    val spaceRows: List<SpaceRow> get() = spaceRows(spaces, expandedSpaces, focusSpace)

    val tagRows: List<TagRow> get() = tagRows(cards, expandedTags)

    val listCards: List<PageCard> get() = visibleCards(cards, spaces, source, filter)

    /** 1열에서 위아래로 오가는 순서. 공간 다음에 태그. */
    val navItems: List<ListSource>
        get() = spaceRows.map { ListSource.InSpace(it.space.slug) } +
            tagRows.map { ListSource.WithTag(it.path) }

    /** 새 페이지가 들어갈 공간. 고른 공간, 없으면 열린 페이지의 공간, 없으면 루트. */
    val targetSpace: String
        get() = (source as? ListSource.InSpace)?.slug ?: page?.detail?.space ?: ROOT_SPACE

    /** 목록을 새로 받았을 때 고른 공간·태그와 펼침을 맞춘다. 처음이면 하위가 있는 공간을 펼친다. */
    fun withLoaded(spaces: List<Space>, cards: List<PageCard>): MainState {
        val next = copy(spaces = spaces, cards = cards, loadError = null, loaded = true)
        val expanded = if (loaded) {
            expandedSpaces
        } else {
            spaces.mapNotNullTo(mutableSetOf()) { it.parent }
        }
        val keep = source?.takeIf { it in next.copy(expandedSpaces = expanded).navItems }
        val fallback = spaces.firstOrNull { it.slug == ROOT_SPACE } ?: spaces.firstOrNull()
        return next.copy(
            expandedSpaces = expanded,
            source = keep ?: fallback?.let { ListSource.InSpace(it.slug) },
            focusSpace = focusSpace?.takeIf { slug -> spaces.any { it.slug == slug } }
        )
    }
}
