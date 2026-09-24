package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlin.time.TestTimeSource
import madang.api.model.FlowWaitingData
import madang.api.model.FlowWaitingEvent
import madang.api.model.PageCard
import madang.api.model.RunFailedData
import madang.api.model.RunFailedEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunRecord
import madang.api.model.RunRef
import madang.api.model.RunResultStatus
import madang.api.model.RunStartedData
import madang.api.model.RunStartedEvent
import madang.api.model.RunUsage
import madang.api.model.RunVerify

/** 지금 탭의 정렬·30분 창·읽지 않음과 상태 글리프. */
class RunWatchTest {

    private val now = Instant.parse("2026-09-24T12:00:00+09:00")
    private val clock = TestTimeSource()

    private fun at(minutesAgo: Int) = Instant.fromEpochSeconds(
        now.epochSeconds - minutesAgo * 60L
    ).toString()

    private fun doneCard(
        id: String,
        minutesAgo: Int,
        status: RunResultStatus = RunResultStatus.REVIEW
    ) = card(id, updated = at(minutesAgo)).copy(
        lastRun = RunRef(
            n = 1,
            runner = "claude",
            model = "claude-opus-5-5",
            resultStatus = status
        )
    )

    private fun started(page: String, n: Int, minutesAgo: Int) = RunStartedEvent(
        type = RunStartedEvent.Type.RUN_PERIOD_STARTED,
        ts = at(minutesAgo),
        project = NOTES,
        page = page,
        run = n,
        data = RunStartedData(runner = "codex", model = "gpt-6-luna", kind = "small", tier = 1)
    )

    private fun finished(page: String, n: Int, minutesAgo: Int, status: RunResultStatus) =
        RunFinishedEvent(
            type = RunFinishedEvent.Type.RUN_PERIOD_FINISHED,
            ts = at(minutesAgo),
            project = NOTES,
            page = page,
            run = n,
            data = RunRecord(
                n = n,
                finished = at(minutesAgo),
                runner = "codex",
                model = "gpt-6-luna",
                usage = RunUsage(0, 0, 0),
                changedFiles = emptyList(),
                unknownFiles = emptyList(),
                verify = RunVerify(),
                resultStatus = status
            )
        )

    private fun waiting(page: String) = FlowWaitingEvent(
        type = FlowWaitingEvent.Type.FLOW_PERIOD_WAITING,
        ts = at(0),
        project = NOTES,
        page = page,
        data = FlowWaitingData(reason = "no_runner")
    )

    private fun active(vararg events: RunStartedEvent): Map<String, ActiveRun> =
        events.fold(emptyMap()) { runs, event -> runs.withRunEvent(event, clock::markNow) }

    @Test
    fun runningComesFirstThenWaitingThenRecentNewestFirst() {
        val cards = listOf(
            doneCard("old-done", minutesAgo = 20),
            doneCard("new-done", minutesAgo = 5),
            card("asking"),
            card("early"),
            card("late")
        )
        val running =
            active(started("early", 1, minutesAgo = 10), started("late", 2, minutesAgo = 2))
        val watch = RunWatch().withEvent(waiting("asking"), running, openPage = null)

        val items = nowItems(cards, running, watch, now)

        assertEquals(
            listOf("late", "early", "asking", "new-done", "old-done"),
            items.map {
                it.page
            }
        )
        assertEquals(
            listOf(
                RunGlyph.RUNNING,
                RunGlyph.RUNNING,
                RunGlyph.NEEDS_HUMAN,
                RunGlyph.DONE,
                RunGlyph.DONE
            ),
            items.map { it.glyph }
        )
    }

    @Test
    fun finishedRunsOlderThanThirtyMinutesAreLeftOut() {
        val cards =
            listOf(doneCard("inside", minutesAgo = 29), doneCard("outside", minutesAgo = 31))
        val watch = RunWatch()
            .withEvent(finished("event-old", 1, 45, RunResultStatus.DONE), emptyMap(), null)
            .withEvent(finished("event-new", 1, 1, RunResultStatus.DONE), emptyMap(), null)

        val items = nowItems(cards, emptyMap(), watch, now)

        assertEquals(listOf("event-new", "inside"), items.map { it.page })
    }

    @Test
    fun eventFinishTimeWinsOverTheCardUpdate() {
        val cards = listOf(doneCard("p", minutesAgo = 50))
        val watch = RunWatch().withEvent(
            finished("p", 2, 3, RunResultStatus.ERROR),
            emptyMap(),
            null
        )

        val item = nowItems(cards, emptyMap(), watch, now).single()

        assertEquals(2, item.n)
        assertEquals(RunGlyph.FAILED, item.glyph)
    }

    @Test
    fun runsEndingOnAnotherPageStayUnreadUntilOpened() {
        val watch = RunWatch()
            .withEvent(
                finished("elsewhere", 1, 1, RunResultStatus.DONE),
                emptyMap(),
                openPage = "here"
            )
            .withEvent(finished("here", 1, 1, RunResultStatus.DONE), emptyMap(), openPage = "here")

        assertEquals(setOf("elsewhere"), watch.unread)
        val items = nowItems(listOf(card("elsewhere"), card("here")), emptyMap(), watch, now)
        assertEquals(
            mapOf("elsewhere" to true, "here" to false),
            items.associate {
                it.page to
                    it.unread
            }
        )
        assertTrue(watch.read("elsewhere").unread.isEmpty())
    }

    @Test
    fun glyphFollowsRunStateAndResult() {
        val failedRun = RunFailedEvent(
            type = RunFailedEvent.Type.RUN_PERIOD_FAILED,
            ts = at(0),
            project = NOTES,
            page = "p",
            run = 1,
            data = RunFailedData(RunResultStatus.CANCELLED, "cancelled")
        )
        val running = active(started("p", 1, 1))
        val card: PageCard = card("p")

        assertEquals(RunGlyph.IDLE, glyphOf("p", card, emptyMap(), RunWatch()))
        assertEquals(RunGlyph.RUNNING, glyphOf("p", card, running, RunWatch()))
        val failed = RunWatch().withEvent(failedRun, running, null)
        assertEquals(RunGlyph.FAILED, glyphOf("p", card, emptyMap(), failed))
        assertEquals("codex", failed.finished.getValue("p").runner)
        val asking = failed.withEvent(waiting("p"), emptyMap(), null)
        assertEquals(RunGlyph.NEEDS_HUMAN, glyphOf("p", card, emptyMap(), asking))
        val resumed = asking.withEvent(started("p", 2, 0), emptyMap(), null)
        assertFalse("p" in resumed.waiting)
        assertEquals(RunGlyph.DONE, resultGlyph(RunResultStatus.REVIEW))
        assertEquals(RunGlyph.FAILED, resultGlyph(RunResultStatus.BLOCKED))
    }
}
