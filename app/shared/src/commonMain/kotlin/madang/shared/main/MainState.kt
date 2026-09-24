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

/** 3열에 열린 페이지. [contents]는 doc·data 블록 id별 파일 내용이다. */
data class OpenPage(val detail: PageDetail, val contents: Map<String, String> = emptyMap())

/**
 * 레이어 0 상태.
 *
 * @property source 1열에서 고른 공간 또는 태그. 2열이 이것을 보여 준다.
 * @property focusSpace 공간 포커스. 있으면 1열에 그 공간과 하위만 보인다.
 * @property selectedPage 2열에서 고른 페이지. [page]는 그 페이지를 불러온 결과다.
 * @property pane 키보드 포커스가 있는 열.
 * @property toggled 접힘 규칙과 반대로 둔 본문 항목의 key.
 * @property activeRuns 페이지 id별 진행 중인 run.
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
    val activeRuns: Map<String, ActiveRun> = emptyMap()
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
