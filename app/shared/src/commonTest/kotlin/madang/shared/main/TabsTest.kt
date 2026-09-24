package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.RunRecord
import madang.api.model.RunUsage
import madang.api.model.RunVerify

class TabsTest {

    private val doc = BlockTab.Block("b02")
    private val data = BlockTab.Block("b03")
    private val run = BlockTab.Run(1)

    private val page = PageDetail(
        id = "resume",
        space = "jobs",
        title = "이력서",
        status = PageStatus.DOING,
        pinned = false,
        tags = emptyList(),
        blocks = listOf(
            BlockHeader(id = "b01", type = BlockType.MESSAGE, text = "hi"),
            BlockHeader(id = "b02", type = BlockType.DOC, file = "blocks/b02-notes.md"),
            BlockHeader(id = "b03", type = BlockType.DATA, title = "base.json"),
            BlockHeader(id = "b04", type = BlockType.VIEW, title = "이력서")
        ),
        runs = listOf(
            RunRecord(
                n = 1,
                usage = RunUsage(input = 10, cached = 0, output = 2),
                changedFiles = emptyList(),
                unknownFiles = emptyList(),
                verify = RunVerify()
            )
        ),
        unknownFiles = emptyList()
    )

    @Test
    fun openAddsTheTabAndMakesItActive() {
        val tabs = TabSet().open(doc).open(run)

        assertEquals(listOf(doc, run), tabs.tabs)
        assertEquals(run, tabs.active)
    }

    @Test
    fun openingAnOpenTabOnlyMovesToIt() {
        val tabs = TabSet().open(doc).open(run).open(doc)

        assertEquals(listOf(doc, run), tabs.tabs)
        assertEquals(doc, tabs.active)
    }

    @Test
    fun closingTheActiveTabActivatesItsNeighbour() {
        val tabs = TabSet().open(doc).open(data).open(run).activate(data)

        assertEquals(TabSet(listOf(doc, run), run), tabs.close(data))
        assertEquals(TabSet(listOf(doc, data), data), tabs.activate(run).close(run))
        assertEquals(TabSet(), TabSet().open(doc).close(doc))
        assertEquals(TabSet(listOf(data, run), data), tabs.close(doc))
    }

    @Test
    fun thePageTabCannotBeClosed() {
        val onPage = TabSet().open(doc).activate(null)

        assertEquals(onPage, onPage.closeActive())
        assertEquals(TabSet(listOf(doc), null), onPage.close(BlockTab.Block("missing")))
    }

    @Test
    fun nextAndPreviousCycleThroughThePageTab() {
        val tabs = TabSet().open(doc).open(run).activate(null)

        assertEquals(doc, tabs.next().active)
        assertEquals(run, tabs.next().next().active)
        assertNull(tabs.next().next().next().active)
        assertEquals(run, tabs.previous().active)
        assertNull(TabSet().next().active)
    }

    @Test
    fun onlyDocDataAndRunItemsOpenTabs() {
        val flow = pageFlow(page)

        assertEquals(listOf(null, doc, data, null, run), flow.map(::tabFor))
    }

    @Test
    fun tabsOfVanishedBlocksAreClosed() {
        val tabs = TabSet().open(doc).open(BlockTab.Block("b09")).open(BlockTab.Run(7))

        assertEquals(TabSet(listOf(doc), doc), tabs.retainIn(page))
    }

    @Test
    fun sendTargetFollowsTheActiveTab() {
        val tabs = TabSet().open(doc).open(data).open(run)

        assertEquals(SendTarget("resume"), sendTarget(page, tabs.activate(null)))
        assertEquals(
            SendTarget("resume", "b02", "b02-notes.md"),
            sendTarget(page, tabs.activate(doc))
        )
        assertEquals(
            SendTarget("resume", "b03", "base.json"),
            sendTarget(page, tabs.activate(data))
        )
        assertEquals(SendTarget("resume"), sendTarget(page, tabs))
    }

    @Test
    fun tabNamesUseTitleThenFileThenId() {
        assertEquals("b02-notes.md", tabName(doc, page))
        assertEquals("base.json", tabName(data, page))
        assertEquals("run 1", tabName(run, page))
        assertEquals("b09", tabName(BlockTab.Block("b09"), page))
    }
}
