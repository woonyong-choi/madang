package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Instant
import kotlinx.datetime.TimeZone
import madang.api.model.PageStatus
import madang.api.model.ProjectSort

class PageListTest {

    private val seoul = TimeZone.of("Asia/Seoul")
    private val now = Instant.parse("2026-09-24T12:00:00+09:00")

    private fun ids(source: ListSource, filter: PageFilter = PageFilter()) =
        visibleCards(Home.cards, Home.projects, source, filter).map { it.id }

    @Test
    fun pinnedFirstThenUpdatedNewestFirst() {
        assertEquals(
            listOf("resume", "cover", "posting"),
            sortCards(listOf(Home.posting, Home.cover, Home.resume), ProjectSort.UPDATED).map {
                it.id
            }
        )
    }

    @Test
    fun createdSortUsesCreatedNewestFirst() {
        val unpinned = Home.cards.map { it.copy(pinned = false) }

        assertEquals(
            listOf("posting", "draft", "resume", "cover"),
            sortCards(unpinned, ProjectSort.CREATED).map { it.id }
        )
    }

    @Test
    fun titleSortIsAlphabeticalAfterPinned() {
        assertEquals(
            listOf("resume", "draft", "posting", "cover"),
            sortCards(Home.cards, ProjectSort.TITLE).map { it.id }
        )
    }

    @Test
    fun updatedSortComparesInstantsAcrossOffsets() {
        val utcLater = card("utc", updated = "2026-09-24T01:00:00Z")
        val seoulEarlier = card("kst", updated = "2026-09-24T09:30:00+09:00")

        assertEquals(
            listOf("utc", "kst"),
            sortCards(listOf(seoulEarlier, utcLater), ProjectSort.UPDATED).map { it.id }
        )
    }

    @Test
    fun projectListIncludesSubprojectsAndUsesThatProjectSort() {
        assertEquals(listOf("resume", "cover", "posting"), ids(ListSource.InProject("jobs")))
        assertEquals(listOf("cover"), ids(ListSource.InProject("jobs-2026")))
        assertEquals(emptyList(), ids(ListSource.InProject(NOTES)))
        assertEquals(ProjectSort.CREATED, sortOf(ListSource.InProject("blog"), Home.projects))
        assertEquals(ProjectSort.UPDATED, sortOf(ListSource.WithTag("글"), Home.projects))
    }

    @Test
    fun tagListIncludesChildTags() {
        assertEquals(listOf("resume", "posting"), ids(ListSource.WithTag("이력서")))
        assertEquals(listOf("posting"), ids(ListSource.WithTag("이력서/공고")))
    }

    @Test
    fun filterByStatusAndTag() {
        val jobs = ListSource.InProject("jobs")

        assertEquals(
            listOf("resume", "posting"),
            ids(jobs, PageFilter(statuses = setOf(PageStatus.DOING, PageStatus.REVIEW)))
        )
        assertEquals(listOf("resume", "posting"), ids(jobs, PageFilter(tags = setOf("이력서"))))
        assertEquals(
            listOf("posting"),
            ids(jobs, PageFilter(statuses = setOf(PageStatus.REVIEW), tags = setOf("이력서")))
        )
        assertEquals(emptyList(), ids(jobs, PageFilter(tags = setOf("글"))))
    }

    @Test
    fun sectionsGroupPinnedThenByDate() {
        val cards = listOf(
            Home.resume,
            card("today", updated = "2026-09-24T08:00:00+09:00"),
            card("yesterday", updated = "2026-09-23T23:59:00+09:00"),
            card("week", updated = "2026-09-19T10:00:00+09:00"),
            card("month", updated = "2026-09-01T10:00:00+09:00"),
            card("august", updated = "2026-07-10T10:00:00+09:00"),
            card("old", updated = "2025-12-31T10:00:00+09:00"),
            card("undated")
        )

        val sections = listSections(cards, ProjectSort.UPDATED, now, seoul)

        assertEquals(
            listOf(
                SectionHeader.Pinned,
                SectionHeader.Today,
                SectionHeader.Yesterday,
                SectionHeader.Previous7Days,
                SectionHeader.Previous30Days,
                SectionHeader.Month(2026, 7),
                SectionHeader.Year(2025),
                SectionHeader.Plain
            ),
            sections.map { it.header }
        )
        assertEquals(cards, sections.flatMap { it.cards })
    }

    @Test
    fun titleSortHasOnlyPinnedAndPlainSections() {
        val sorted = sortCards(Home.cards, ProjectSort.TITLE)

        val sections = listSections(sorted, ProjectSort.TITLE, now, seoul)

        assertEquals(listOf(SectionHeader.Pinned, SectionHeader.Plain), sections.map { it.header })
    }

    @Test
    fun projectTreeFocusShowsOnlyThatSubtree() {
        val rows = projectRows(Home.projects, expanded = setOf("jobs"), focus = "jobs")

        assertEquals(listOf("jobs" to 0, "jobs-2026" to 1), rows.map { it.project.id to it.depth })
        assertEquals(setOf("jobs", "jobs-2026"), projectWithDescendants("jobs", Home.projects))
    }

    @Test
    fun projectStatsCountPagesAndActiveWork() {
        val stats = projectStats(Home.cards)

        assertEquals(ProjectStats(pages = 2, active = true), stats["jobs"])
        assertEquals(ProjectStats(pages = 1, active = false), stats["jobs-2026"])
        assertEquals(ProjectStats(pages = 1, active = true), stats["blog"])
    }

    @Test
    fun tagTreeCountsPagesWithChildTags() {
        val collapsed = tagRows(Home.cards, expanded = emptySet())
        assertEquals(listOf("글" to 1, "이력서" to 2), collapsed.map { it.path to it.count })

        val expanded = tagRows(Home.cards, expanded = setOf("이력서"))
        assertEquals(
            listOf("글", "이력서", "이력서/공고"),
            expanded.map { it.path }
        )
        assertEquals("공고", expanded.last().name)
        assertEquals(1, expanded.last().depth)
    }
}
