package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import madang.api.model.RunRecord
import madang.api.model.RunResultStatus
import madang.api.model.RunUsage
import madang.api.model.RunVerify
import madang.shared.core.decodeEvent

/** 결과 블록의 머지·게시 상태를 되돌리기 기록·묻는 블록·이벤트라는 사실만으로 정하는지 본다. */
class OutcomeTest {

    @Test
    fun undoLogGivesTheMergeAndPublishOfTheRun() {
        val log = assertNotNullLog(UNDO_JSON)

        val outcome = runOutcome(run(3), log, emptySet(), SettleWatch())

        assertEquals(SettleState.DONE, outcome.settle)
        assertEquals("7b8c9d0e1f2a", outcome.merged)
        assertEquals(4, outcome.published)
        assertFalse(outcome.undone)
    }

    @Test
    fun undoLogOfAnotherRunIsNotUsed() {
        val log = assertNotNullLog(UNDO_JSON)

        val outcome = runOutcome(run(4), log, emptySet(), SettleWatch())

        assertNull(outcome.settle)
        assertNull(outcome.merged)
    }

    @Test
    fun undoneLogMarksTheResultUndone() {
        val log = assertNotNullLog(UNDO_JSON.replace("\"undone\": null", "\"undone\": \"t\""))

        assertTrue(runOutcome(run(3), log, emptySet(), SettleWatch()).undone)
    }

    @Test
    fun brokenUndoLogIsIgnored() {
        assertNull(parseUndoLog("{"))
        assertNull(parseUndoLog("""{"effects":[]}"""))
    }

    @Test
    fun askCreatedEventOfTheRunMeansRefused() {
        val watch = SettleWatch().withEvent(event("ask.created", ASK, run = 3, block = "b09"))

        assertEquals(setOf(3), watch.asked)
        assertEquals(SettleState.REFUSED, runOutcome(run(3), null, watch.asked, watch).settle)
        assertNull(runOutcome(run(2), null, watch.asked, watch).settle)
    }

    @Test
    fun mergeAfterAnAnswerWinsOverTheAskBlock() {
        val log = assertNotNullLog(UNDO_JSON)

        val outcome = runOutcome(run(3), log, setOf(3), SettleWatch())

        assertEquals(SettleState.DONE, outcome.settle)
    }

    @Test
    fun busyFlowMeansPendingUntilCoreReportsMoreFacts() {
        assertEquals(
            SettleState.PENDING,
            runOutcome(run(3), null, emptySet(), SettleWatch(), flowBusy = true).settle
        )
        assertNull(runOutcome(run(3), null, emptySet(), SettleWatch()).settle)
    }

    @Test
    fun publishEventGivesThePublishNumber() {
        val published = SettleWatch().withEvent(
            event("publish.done", """{"n":4,"undo":false}""", 3)
        )

        assertEquals(mapOf(3 to 4), published.published)
        val outcome = runOutcome(run(3), null, emptySet(), published, flowBusy = true)
        assertEquals(SettleState.DONE, outcome.settle)
        assertEquals(4, outcome.published)
    }

    @Test
    fun undoPublishEventIsNotAPublish() {
        val watch = SettleWatch().withEvent(event("publish.done", """{"n":4,"undo":true}""", 3))

        assertTrue(watch.published.isEmpty())
    }

    @Test
    fun resultBlockIsTheLastFinishedRun() {
        val running = run(4).copy(resultStatus = null, finished = null)

        assertEquals(3, lastFinishedRun(listOf(run(2), run(3), running))?.n)
        assertNull(lastFinishedRun(listOf(running)))
    }

    private fun assertNotNullLog(text: String): UndoLog =
        kotlin.test.assertNotNull(parseUndoLog(text))

    private fun run(n: Int) = RunRecord(
        n = n,
        usage = RunUsage(input = 1, cached = 0, output = 1),
        changedFiles = emptyList(),
        unknownFiles = emptyList(),
        verify = RunVerify(),
        finished = "2026-09-24T10:00:00+09:00",
        resultStatus = RunResultStatus.DONE
    )

    private fun event(
        type: String,
        data: String,
        run: Int? = null,
        page: String? = "resume",
        block: String? = null
    ): Any {
        val fields = listOfNotNull(
            page?.let { ""","page":"$it"""" },
            run?.let { ""","run":$it""" },
            block?.let { ""","block":"$it"""" }
        ).joinToString("")
        val frame = """{"type":"$type","ts":"t","project":"jobs"$fields,"data":$data}"""
        return kotlin.test.assertNotNull(decodeEvent(frame)).payload
    }

    private companion object {
        const val UNDO_JSON = """{"n": 3, "base": {"page.md": "aa"}, "effects": [
            {"kind": "file", "path": "page.md", "before": "aa", "after": "bb"},
            {"kind": "merge", "path": "/work/jobs", "before": "0f", "commit": "7b8c9d0e1f2a"},
            {"kind": "publish", "path": "/work/jobs", "publish": 4}
        ], "undone": null}"""

        const val ASK = """{"block":"b09","decision":"b08","prompt":"멈췄습니다",
            "reasons":["테스트 실패"],"options":["merge","retry","stop"]}"""
    }
}
