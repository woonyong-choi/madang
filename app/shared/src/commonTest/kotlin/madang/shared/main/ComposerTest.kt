package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageDetail
import madang.api.model.PageStatus

class ComposerTest {

    @Test
    fun enterWhileAnInputMethodIsComposingDoesNotSend() {
        assertNull(composerKey(enter = true, shift = false, composing = true))
        assertNull(composerKey(enter = true, shift = true, composing = true))
        assertEquals(ComposerKey.SEND, composerKey(enter = true, shift = false, composing = false))
    }

    @Test
    fun enterSendsShiftEnterBreaksAndOtherKeysPass() {
        assertEquals(ComposerKey.SEND, composerKey(enter = true, shift = false))
        assertEquals(ComposerKey.NEWLINE, composerKey(enter = true, shift = true))
        assertNull(composerKey(enter = false, shift = false))
        assertNull(composerKey(enter = false, shift = true))
    }

    @Test
    fun acceptedMessageLeavesOnceThePageHasIt() {
        val page = OpenPage(detail(listOf("b01")))
            .copy(pending = listOf(PendingMessage("pending-1", "안녕")))
        assertEquals(listOf("b01", "pending-1"), page.flowItems.map { it.key })

        val eventFirst = page.withDetail(detail(listOf("b01", "b02")))
        assertEquals(listOf("b01", "b02", "pending-1"), eventFirst.flowItems.map { it.key })

        val accepted = eventFirst.withAccepted("pending-1", "b02")
        assertEquals(listOf("b01", "b02"), accepted.flowItems.map { it.key })
        assertTrue(accepted.pending.isEmpty())
    }

    private fun detail(userBlocks: List<String>) = PageDetail(
        id = "p",
        project = "root",
        title = "p",
        status = PageStatus.DOING,
        pinned = false,
        tags = emptyList(),
        blocks = userBlocks.map {
            BlockHeader(id = it, type = BlockType.MESSAGE, role = MessageRole.USER, text = it)
        },
        runs = emptyList(),
        unknownFiles = emptyList()
    )
}
