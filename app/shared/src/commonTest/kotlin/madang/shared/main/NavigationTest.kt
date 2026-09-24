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
    fun firstLoadSelectsRootAndExpandsParents() {
        val state = Home.state()

        assertEquals(ListSource.InSpace(ROOT_SPACE), state.source)
        assertEquals(setOf("jobs"), state.expandedSpaces)
        assertEquals(
            listOf(ROOT_SPACE, "blog", "jobs", "jobs-2026"),
            state.spaceRows.map { it.space.slug }
        )
    }

    @Test
    fun upDownMoveThroughSpacesThenTags() {
        val state = Home.state()

        val down = state.press(NavKey.DOWN, NavKey.DOWN).state
        assertEquals(ListSource.InSpace("jobs"), down.source)

        val bottom = state.press(*Array(10) { NavKey.DOWN }).state
        assertEquals(ListSource.WithTag("이력서"), bottom.source)
        assertEquals(bottom.source, bottom.press(NavKey.DOWN).state.source)

        val top = down.press(NavKey.UP, NavKey.UP, NavKey.UP).state
        assertEquals(ListSource.InSpace(ROOT_SPACE), top.source)
    }

    @Test
    fun leftCollapsesThenGoesToParentAndRightExpands() {
        val child = Home.state().copy(source = ListSource.InSpace("jobs-2026"))

        val parent = child.press(NavKey.LEFT).state
        assertEquals(ListSource.InSpace("jobs"), parent.source)

        val collapsed = parent.press(NavKey.LEFT).state
        assertEquals(emptySet(), collapsed.expandedSpaces)
        assertEquals(ListSource.InSpace("jobs"), collapsed.source)

        val expanded = collapsed.press(NavKey.RIGHT).state
        assertEquals(setOf("jobs"), expanded.expandedSpaces)
        assertEquals(Pane.SPACES, expanded.pane)
    }

    @Test
    fun rightOnExpandedSpaceEntersListAndOpensFirstPage() {
        val jobs = Home.state().copy(source = ListSource.InSpace("jobs"))

        val outcome = jobs.press(NavKey.RIGHT)

        assertEquals(Pane.LIST, outcome.state.pane)
        assertEquals("resume", outcome.state.selectedPage)
        assertEquals(KeyEffect.OpenPage("resume"), outcome.effect)
    }

    @Test
    fun enterKeepsSelectedPageWhenItIsListed() {
        val state = Home.state().copy(source = ListSource.InSpace("jobs"), selectedPage = "posting")

        val outcome = state.press(NavKey.ENTER)

        assertEquals(Pane.LIST, outcome.state.pane)
        assertEquals("posting", outcome.state.selectedPage)
        assertNull(outcome.effect)
    }

    @Test
    fun listArrowsSelectAndOpenPagesInDisplayOrder() {
        val list = Home.state(Pane.LIST).copy(source = ListSource.InSpace("jobs"))

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
        val list = Home.state(Pane.LIST).copy(source = ListSource.InSpace("jobs"))

        assertEquals(Pane.LIST, list.press(NavKey.ENTER).state.pane)

        val selected = list.copy(selectedPage = "resume")
        val page = selected.press(NavKey.ENTER).state
        assertEquals(Pane.PAGE, page.pane)

        assertEquals(Pane.LIST, page.press(NavKey.BACK).state.pane)
        assertEquals(Pane.SPACES, page.press(NavKey.BACK, NavKey.BACK).state.pane)
        assertEquals(Pane.SPACES, page.press(NavKey.LEFT, NavKey.LEFT).state.pane)
    }

    @Test
    fun commandDigitsFocusColumnsAndCommandNCreatesPage() {
        val state = Home.state()

        assertEquals(Pane.LIST, state.press(NavKey.FOCUS_LIST).state.pane)
        assertEquals(Pane.PAGE, state.press(NavKey.FOCUS_PAGE).state.pane)
        assertEquals(Pane.SPACES, state.press(NavKey.FOCUS_PAGE, NavKey.FOCUS_SPACES).state.pane)
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
        assertEquals(Pane.entries, visiblePanes(1400f, Pane.SPACES))
        assertEquals(listOf(Pane.SPACES, Pane.PAGE), visiblePanes(900f, Pane.SPACES))
        assertEquals(listOf(Pane.LIST, Pane.PAGE), visiblePanes(900f, Pane.LIST))
        assertEquals(listOf(Pane.LIST, Pane.PAGE), visiblePanes(900f, Pane.PAGE))
        assertEquals(listOf(Pane.PAGE), visiblePanes(500f, Pane.PAGE))
        assertEquals(listOf(Pane.SPACES), visiblePanes(500f, Pane.SPACES))
    }
}
