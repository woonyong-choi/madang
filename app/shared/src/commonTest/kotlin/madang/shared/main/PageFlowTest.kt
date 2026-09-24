package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.time.TestTimeSource
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.RunFinishedEvent
import madang.api.model.RunProgressEvent
import madang.api.model.RunRecord
import madang.api.model.RunStartedData
import madang.api.model.RunStartedEvent
import madang.api.model.RunStreamEvent
import madang.api.model.RunTrigger
import madang.api.model.RunUsage
import madang.api.model.RunVerify

class PageFlowTest {

    private fun message(id: String, role: MessageRole) =
        BlockHeader(id = id, type = BlockType.MESSAGE, role = role, text = id)

    private fun block(id: String, type: BlockType) = BlockHeader(id = id, type = type)

    private fun run(n: Int, trigger: String?) = RunRecord(
        n = n,
        usage = RunUsage(input = 0, cached = 0, output = 0),
        changedFiles = emptyList(),
        unknownFiles = emptyList(),
        verify = RunVerify(),
        trigger = trigger?.let { RunTrigger(message = it) }
    )

    private val page = PageDetail(
        id = "p",
        space = ROOT_SPACE,
        title = "p",
        status = PageStatus.DOING,
        pinned = false,
        tags = emptyList(),
        blocks = listOf(
            message("b01", MessageRole.USER),
            message("b02", MessageRole.ROUTER),
            message("b03", MessageRole.AGENT),
            block("b04", BlockType.VIEW),
            block("b05", BlockType.DATA),
            block("b06", BlockType.DOC),
            message("b07", MessageRole.USER),
            message("b08", MessageRole.ROUTER),
            message("b09", MessageRole.AGENT)
        ),
        runs = listOf(run(1, "b01"), run(2, "b07"), run(3, null)),
        unknownFiles = emptyList()
    )

    @Test
    fun runsFollowTheirTriggerMessage() {
        assertEquals(
            listOf(
                "b01", "run-1", "b02", "b03", "b04", "b05", "b06",
                "b07", "run-2", "b08", "b09", "run-3"
            ),
            pageFlow(page).map { it.key }
        )
    }

    @Test
    fun routerAndRunsFoldAndOldMessagesFold() {
        val folded = foldedKeys(pageFlow(page), expandAll = false, toggled = emptySet())

        assertEquals(
            setOf("b01", "run-1", "b02", "b03", "run-2", "b08", "run-3"),
            folded
        )
    }

    @Test
    fun expandAllAndToggleOverrideRules() {
        val items = pageFlow(page)

        assertEquals(emptySet(), foldedKeys(items, expandAll = true, toggled = setOf("b01")))

        val toggled = foldedKeys(items, expandAll = false, toggled = setOf("b03", "b09"))
        assertEquals(setOf("b01", "run-1", "b02", "run-2", "b08", "b09", "run-3"), toggled)
    }

    @Test
    fun jsonArrayOfObjectsBecomesTable() {
        val preview = dataPreview(
            """[{"company":"펄어비스","period":"2019"},{"company":"한빛","role":"lead"}]"""
        )!!

        assertEquals(listOf("company", "period", "role"), preview.columns)
        assertEquals(listOf(listOf("펄어비스", "2019", ""), listOf("한빛", "", "lead")), preview.rows)
        assertEquals(2, preview.rowCount)
    }

    @Test
    fun jsonObjectBecomesKeyValueRows() {
        val preview = dataPreview("""{"name":"김마당","work":[1,2],"contact":{"a":1}}""")!!

        assertEquals(listOf("key", "value"), preview.columns)
        assertEquals(
            listOf(listOf("name", "김마당"), listOf("work", "[2]"), listOf("contact", "{1}")),
            preview.rows
        )
        assertEquals(3, preview.rowCount)
    }

    @Test
    fun csvAndInvalidContent() {
        val csv = dataPreview("a,b\n1,2\n3,4\n", csv = true)!!
        assertEquals(listOf("a", "b"), csv.columns)
        assertEquals(2, csv.rowCount)

        assertNull(dataPreview("not json"))
        assertEquals(7, dataPreview((1..7).joinToString(",", "[", "]"))!!.rowCount)
        assertEquals(5, dataPreview((1..7).joinToString(",", "[", "]"))!!.rows.size)
    }

    @Test
    fun runEventsTrackActiveRunPerPage() {
        val clock = TestTimeSource()
        val started = RunStartedEvent(
            type = RunStartedEvent.Type.RUN_PERIOD_STARTED,
            ts = "t",
            space = "jobs",
            page = "p",
            run = 2,
            data = RunStartedData(runner = "codex", model = "gpt-6-luna", kind = "small", tier = 1)
        )
        val progress = RunProgressEvent(
            type = RunProgressEvent.Type.RUN_PERIOD_PROGRESS,
            ts = "t",
            space = "jobs",
            page = "p",
            run = 2,
            data = RunStreamEvent(type = RunStreamEvent.Type.FILE_CHANGED, path = "a.json")
        )
        val finished = RunFinishedEvent(
            type = RunFinishedEvent.Type.RUN_PERIOD_FINISHED,
            ts = "t",
            space = "jobs",
            page = "p",
            run = 2,
            data = run(2, null)
        )

        val running = emptyMap<String, ActiveRun>()
            .withRunEvent(started, clock::markNow)
            .withRunEvent(progress, clock::markNow)

        val active = running.getValue("p")
        assertEquals("codex" to "gpt-6-luna", active.runner to active.model)
        assertEquals(RunActivity.Progress(progress.data), active.last)
        assertEquals(emptyMap(), running.withRunEvent(finished, clock::markNow))
        assertEquals(running, running.withRunEvent(finished.copy(run = 9), clock::markNow))
    }
}
