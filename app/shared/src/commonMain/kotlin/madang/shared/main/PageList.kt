package madang.shared.main

import kotlin.time.Instant
import kotlinx.datetime.DatePeriod
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.minus
import kotlinx.datetime.toLocalDateTime
import madang.api.model.PageCard
import madang.api.model.PageStatus
import madang.api.model.Space
import madang.api.model.SpaceSort

/** 2열이 보여 주는 대상. 1열에서 고른 공간 또는 태그. */
sealed interface ListSource {
    data class InSpace(val slug: String) : ListSource

    data class WithTag(val path: String) : ListSource
}

/** 2열 필터. 비어 있는 조건은 거르지 않는다. 태그는 하위 태그도 맞는 것으로 본다. */
data class PageFilter(
    val statuses: Set<PageStatus> = emptySet(),
    val tags: Set<String> = emptySet()
) {
    val isActive: Boolean get() = statuses.isNotEmpty() || tags.isNotEmpty()

    fun matches(card: PageCard): Boolean {
        val statusOk = statuses.isEmpty() || card.status in statuses
        val tagOk =
            tags.isEmpty() || tags.any { filter -> card.tags.any { tagMatches(it, filter) } }
        return statusOk && tagOk
    }
}

/**
 * 2열에 보일 카드를 순서대로 돌려준다.
 *
 * 공간이면 그 공간과 하위 공간의 페이지를 공간의 정렬로, 태그면 그 태그(하위 포함)를 가진
 * 페이지를 갱신순으로 보인다. 고정된 페이지가 먼저다.
 */
fun visibleCards(
    cards: List<PageCard>,
    spaces: List<Space>,
    source: ListSource?,
    filter: PageFilter
): List<PageCard> {
    val picked = when (source) {
        null -> return emptyList()

        is ListSource.InSpace -> {
            val slugs = spaceWithDescendants(source.slug, spaces)
            cards.filter { it.space in slugs }
        }

        is ListSource.WithTag -> cards.filter { card ->
            card.tags.any { tagMatches(it, source.path) }
        }
    }
    return sortCards(picked.filter(filter::matches), sortOf(source, spaces))
}

/** [source]의 정렬. 공간은 공간 설정(기본 갱신순), 태그는 갱신순. */
fun sortOf(source: ListSource?, spaces: List<Space>): SpaceSort = when (source) {
    is ListSource.InSpace -> spaces.firstOrNull { it.slug == source.slug }?.sort
        ?: SpaceSort.UPDATED

    else -> SpaceSort.UPDATED
}

/** 고정 먼저, 그다음 [sort]. 갱신·생성은 최신이 위, 제목은 가나다·abc순. */
fun sortCards(cards: List<PageCard>, sort: SpaceSort): List<PageCard> {
    val byKey: Comparator<PageCard> = when (sort) {
        SpaceSort.UPDATED -> compareByDescending { instantOrNull(it.updated) }
        SpaceSort.CREATED -> compareByDescending { instantOrNull(it.created) }
        SpaceSort.TITLE -> compareBy { it.title.lowercase() }
    }
    return cards.sortedWith(
        compareByDescending<PageCard> { it.pinned }
            .then(byKey)
            .thenBy { it.title.lowercase() }
            .thenBy { it.id }
    )
}

/** 2열 목록의 묶음 머리. 날짜순일 때 날짜별로 묶는다. */
sealed interface SectionHeader {
    data object Pinned : SectionHeader

    data object Today : SectionHeader

    data object Yesterday : SectionHeader

    data object Previous7Days : SectionHeader

    data object Previous30Days : SectionHeader

    data class Month(val year: Int, val month: Int) : SectionHeader

    data class Year(val year: Int) : SectionHeader

    /** 제목순이거나 날짜가 없는 페이지. 머리를 그리지 않는다. */
    data object Plain : SectionHeader
}

data class ListSection(val header: SectionHeader, val cards: List<PageCard>)

/**
 * 정렬된 카드를 묶음으로 나눈다. 고정된 페이지가 첫 묶음이고, 날짜순이면 나머지를
 * 오늘·어제·지난 7일·지난 30일·월·연도로 묶는다. 카드 순서는 바꾸지 않는다.
 */
fun listSections(
    sorted: List<PageCard>,
    sort: SpaceSort,
    now: Instant,
    zone: TimeZone
): List<ListSection> {
    val today = now.toLocalDateTime(zone).date
    val sections = mutableListOf<ListSection>()
    for (card in sorted) {
        val header = when {
            card.pinned -> SectionHeader.Pinned
            sort == SpaceSort.TITLE -> SectionHeader.Plain
            else -> dateHeader(dateOf(card, sort, zone), today)
        }
        val last = sections.lastOrNull()
        if (last?.header == header) {
            sections[sections.lastIndex] = last.copy(cards = last.cards + card)
        } else {
            sections += ListSection(header, listOf(card))
        }
    }
    return sections
}

private fun dateOf(card: PageCard, sort: SpaceSort, zone: TimeZone): LocalDate? {
    val stamp = if (sort == SpaceSort.CREATED) card.created else card.updated
    return instantOrNull(stamp)?.toLocalDateTime(zone)?.date
}

private fun dateHeader(date: LocalDate?, today: LocalDate): SectionHeader = when {
    date == null -> SectionHeader.Plain
    date >= today -> SectionHeader.Today
    date == today.minus(DatePeriod(days = 1)) -> SectionHeader.Yesterday
    date > today.minus(DatePeriod(days = 7)) -> SectionHeader.Previous7Days
    date > today.minus(DatePeriod(days = 30)) -> SectionHeader.Previous30Days
    date.year == today.year -> SectionHeader.Month(date.year, date.month.ordinal + 1)
    else -> SectionHeader.Year(date.year)
}

/** ISO 8601 시각. 없거나 형식이 틀리면 null. */
fun instantOrNull(stamp: String?): Instant? =
    stamp?.let { runCatching { Instant.parse(it) }.getOrNull() }
