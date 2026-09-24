package madang.shared.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import madang.api.model.EventType
import madang.api.model.RunProgressEvent

class EventStreamTest {

    private val progress = """
        {"type":"run.progress","ts":"2026-09-24T09:31:12+09:00","project":"jobs",
         "page":"2026-09-24-resume","run":2,
         "data":{"type":"file_changed","path":"blocks/b05-base.json"}}
    """.trimIndent()

    private val pageDeleted = """
        {"type":"page.deleted","ts":"2026-09-24T10:00:00+09:00","project":"jobs",
         "page":"2026-09-20-old","data":{"id":"2026-09-20-old"}}
    """.trimIndent()

    @Test
    fun decodesEnvelopeThenConcreteEvent() {
        val event = decodeEvent(progress)!!

        assertEquals(EventType.RUN_PERIOD_PROGRESS, event.envelope.type)
        val payload = assertIs<RunProgressEvent>(event.payload)
        assertEquals(2, payload.run)
        assertEquals("blocks/b05-base.json", payload.`data`.path)
    }

    @Test
    fun ignoresUnknownOrBrokenFrames() {
        assertNull(decodeEvent("""{"type":"project.renamed","ts":"2026-09-24T10:00:00+09:00"}"""))
        assertNull(decodeEvent("not json"))
    }

    @Test
    fun reconnectsAndAsksForResync() = runTest {
        var connections = 0
        val transport = EventTransport { onOpen, onFrame ->
            connections++
            when (connections) {
                1 -> {
                    onOpen()
                    onFrame(progress)
                    onFrame("""{"type":"unknown.kind","ts":"x"}""")
                    throw IllegalStateException("socket closed")
                }

                2 -> throw IllegalStateException("connection refused")

                else -> {
                    onOpen()
                    onFrame(pageDeleted)
                    awaitCancellation()
                }
            }
        }

        val items = EventStream(transport).items().take(6).toList()

        assertEquals(EventStreamItem.Resync(reconnected = false), items[0])
        assertEquals(EventType.RUN_PERIOD_PROGRESS, received(items[1]))
        assertEquals(EventStreamItem.Disconnected("socket closed", 1.seconds), items[2])
        assertEquals(EventStreamItem.Disconnected("connection refused", 2.seconds), items[3])
        assertEquals(EventStreamItem.Resync(reconnected = true), items[4])
        assertEquals(EventType.PAGE_PERIOD_DELETED, received(items[5]))
    }

    @Test
    fun backoffResetsAfterSuccessfulOpen() = runTest {
        var connections = 0
        val transport = EventTransport { onOpen, _ ->
            connections++
            if (connections == 2) onOpen()
            throw IllegalStateException("drop $connections")
        }

        val items = EventStream(transport).items().take(4).toList()

        assertEquals(EventStreamItem.Disconnected("drop 1", 1.seconds), items[0])
        assertEquals(EventStreamItem.Resync(reconnected = false), items[1])
        assertEquals(EventStreamItem.Disconnected("drop 2", 1.seconds), items[2])
        assertEquals(EventStreamItem.Disconnected("drop 3", 2.seconds), items[3])
    }

    @Test
    fun backoffIsCapped() {
        assertEquals(1.seconds, EventStream.backoff(1))
        assertEquals(8.seconds, EventStream.backoff(4))
        assertEquals(15.seconds, EventStream.backoff(9))
    }

    private fun received(item: EventStreamItem): EventType =
        assertIs<EventStreamItem.Received>(item).event.envelope.type
}
