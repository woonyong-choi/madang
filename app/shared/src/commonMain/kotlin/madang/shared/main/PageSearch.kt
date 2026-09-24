package madang.shared.main

import madang.api.model.PageCard

/**
 * 페이지 검색(Cmd/Ctrl+K). 제목·마지막 메시지·태그에 [query]의 모든 낱말이 들어간 카드.
 *
 * 제목이 검색어로 시작하는 것, 제목에 들어간 것, 나머지 순이고 같은 순위면 최근 갱신이 먼저다.
 * 검색어가 비었으면 최근 갱신순 전체다.
 */
fun searchPages(cards: List<PageCard>, query: String, limit: Int = SEARCH_LIMIT): List<PageCard> {
    val words = query.lowercase().split(' ').filter { it.isNotBlank() }
    val recent = cards.sortedByDescending { it.updated.orEmpty() }
    if (words.isEmpty()) return recent.take(limit)
    val phrase = words.joinToString(" ")
    return recent
        .filter { card -> words.all { it in card.searchText() } }
        .sortedBy { card ->
            val title = card.title.lowercase()
            when {
                title.startsWith(phrase) -> 0
                phrase in title -> 1
                else -> 2
            }
        }
        .take(limit)
}

private fun PageCard.searchText(): String =
    listOf(title, preview.orEmpty(), tags.joinToString(" ") { "#$it" }).joinToString(" ")
        .lowercase()

private const val SEARCH_LIMIT = 30
