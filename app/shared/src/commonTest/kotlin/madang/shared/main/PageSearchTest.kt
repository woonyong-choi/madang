package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals

class PageSearchTest {

    private val cards = listOf(
        Home.resume.copy(preview = "요약문 다듬기"),
        Home.posting.copy(preview = "기술 일치 8/10"),
        Home.cover.copy(title = "자기소개서 (이력서 첨부)"),
        Home.draft
    )

    @Test
    fun emptyQueryListsRecentPagesFirst() {
        assertEquals(
            listOf("cover", "resume", "posting", "draft"),
            searchPages(cards, " ").map {
                it.id
            }
        )
    }

    @Test
    fun titlePrefixRanksAboveTitleAndTextMatches() {
        assertEquals(listOf("resume", "cover", "posting"), searchPages(cards, "이력서").map { it.id })
    }

    @Test
    fun everyWordMustMatchTitlePreviewOrTag() {
        assertEquals(listOf("resume"), searchPages(cards, "요약문 #이력서").map { it.id })
        assertEquals(listOf("posting"), searchPages(cards, "기술").map { it.id })
        assertEquals(emptyList(), searchPages(cards, "없는말").map { it.id })
    }
}
