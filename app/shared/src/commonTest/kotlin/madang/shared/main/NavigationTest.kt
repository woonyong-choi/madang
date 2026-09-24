package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class NavigationTest {

    private fun MainState.press(vararg keys: NavKey): KeyOutcome {
        var outcome = KeyOutcome(this)
        for (key in keys) outcome = outcome.state.onKey(key)
        return outcome
    }

    @Test
    fun firstLoadSelectsFirstProjectAndExpandsParents() {
        val state = Home.state()

        assertEquals(ListSource.InProject(NOTES), state.source)
        assertEquals(setOf("jobs"), state.expandedProjects)
        assertEquals(
            listOf(NOTES, "blog", "jobs", "jobs-2026"),
            state.projectRows.map { it.project.id }
        )
    }

    @Test
    fun upDownMoveThroughProjectsThenTags() {
        val state = Home.state()

        val down = state.press(NavKey.DOWN, NavKey.DOWN).state
        assertEquals(ListSource.InProject("jobs"), down.source)

        val bottom = state.press(*Array(10) { NavKey.DOWN }).state
        assertEquals(ListSource.WithTag("이력서"), bottom.source)
        assertEquals(bottom.source, bottom.press(NavKey.DOWN).state.source)

        val top = down.press(NavKey.UP, NavKey.UP, NavKey.UP).state
        assertEquals(ListSource.InProject(NOTES), top.source)
    }

    @Test
    fun leftCollapsesThenGoesToParentAndRightExpands() {
        val child = Home.state().copy(source = ListSource.InProject("jobs-2026"))

        val parent = child.press(NavKey.LEFT).state
        assertEquals(ListSource.InProject("jobs"), parent.source)

        val collapsed = parent.press(NavKey.LEFT).state
        assertEquals(emptySet(), collapsed.expandedProjects)
        assertEquals(ListSource.InProject("jobs"), collapsed.source)

        val expanded = collapsed.press(NavKey.RIGHT).state
        assertEquals(setOf("jobs"), expanded.expandedProjects)
        assertEquals(Pane.PROJECTS, expanded.pane)
    }

    @Test
    fun rightOnExpandedProjectEntersListAndOpensFirstPage() {
        val jobs = Home.state().copy(source = ListSource.InProject("jobs"))

        val outcome = jobs.press(NavKey.RIGHT)

        assertEquals(Pane.LIST, outcome.state.pane)
        assertEquals("resume", outcome.state.selectedPage)
        assertEquals(KeyEffect.OpenPage("resume"), outcome.effect)
    }

    @Test
    fun enterKeepsSelectedPageWhenItIsListed() {
        val state = Home.state().copy(
            source = ListSource.InProject("jobs"),
            selectedPage = "posting"
        )

        val outcome = state.press(NavKey.ENTER)

        assertEquals(Pane.LIST, outcome.state.pane)
        assertEquals("posting", outcome.state.selectedPage)
        assertNull(outcome.effect)
    }

    @Test
    fun listArrowsSelectAndOpenPagesInDisplayOrder() {
        val list = Home.state(Pane.LIST).copy(source = ListSource.InProject("jobs"))

        val first = list.press(NavKey.DOWN)
        assertEquals(KeyEffect.OpenPage("resume"), first.effect)

        val second = first.state.press(NavKey.DOWN)
        assertEquals(KeyEffect.OpenPage("cover"), second.effect)

        val third = second.state.press(NavKey.DOWN)
        assertEquals(KeyEffect.OpenPage("posting"), third.effect)

        val end = third.state.press(NavKey.DOWN)
        assertNull(end.effect)
        assertEquals("posting", end.state.selectedPage)

        assertEquals(KeyEffect.OpenPage("cover"), third.state.press(NavKey.UP).effect)
    }

    @Test
    fun enterAndBackspaceMoveBetweenColumns() {
        val list = Home.state(Pane.LIST).copy(source = ListSource.InProject("jobs"))

        assertEquals(Pane.LIST, list.press(NavKey.ENTER).state.pane)

        val selected = list.copy(selectedPage = "resume")
        val page = selected.press(NavKey.ENTER).state
        assertEquals(Pane.PAGE, page.pane)

        assertEquals(Pane.LIST, page.press(NavKey.BACK).state.pane)
        assertEquals(Pane.PROJECTS, page.press(NavKey.BACK, NavKey.BACK).state.pane)
        assertEquals(Pane.PROJECTS, page.press(NavKey.LEFT, NavKey.LEFT).state.pane)
    }

    @Test
    fun commandDigitsFocusColumnsAndCommandNCreatesPage() {
        val state = Home.state()

        assertEquals(Pane.LIST, state.press(NavKey.FOCUS_LIST).state.pane)
        assertEquals(Pane.PAGE, state.press(NavKey.FOCUS_PAGE).state.pane)
        assertEquals(
            Pane.PROJECTS,
            state.press(NavKey.FOCUS_PAGE, NavKey.FOCUS_PROJECTS).state.pane
        )
        assertEquals(KeyEffect.NewPage, state.press(NavKey.NEW_PAGE).effect)
    }

    @Test
    fun tagLeftCollapsesThenGoesToParentTag() {
        val state = Home.state().copy(
            source = ListSource.WithTag("이력서"),
            expandedTags = setOf("이력서")
        )

        val child = state.press(NavKey.DOWN).state
        assertEquals(ListSource.WithTag("이력서/공고"), child.source)

        assertEquals(ListSource.WithTag("이력서"), child.press(NavKey.LEFT).state.source)
        assertEquals(emptySet(), child.press(NavKey.LEFT, NavKey.LEFT).state.expandedTags)
    }

    @Test
    fun panesCollapseWithWidth() {
        assertEquals(Pane.entries, visiblePanes(1400f, Pane.PROJECTS))
        assertEquals(listOf(Pane.PROJECTS, Pane.PAGE), visiblePanes(900f, Pane.PROJECTS))
        assertEquals(listOf(Pane.LIST, Pane.PAGE), visiblePanes(900f, Pane.LIST))
        assertEquals(listOf(Pane.LIST, Pane.PAGE), visiblePanes(900f, Pane.PAGE))
        assertEquals(listOf(Pane.PAGE), visiblePanes(500f, Pane.PAGE))
        assertEquals(listOf(Pane.PROJECTS), visiblePanes(500f, Pane.PROJECTS))
    }
}
