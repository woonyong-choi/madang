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
    fun prefixSuggestionsMatchTheFirstWord() {
        assertEquals(listOf("design:"), prefixSuggestions("de"))
        assertEquals(listOf("small:"), prefixSuggestions("S"))
        assertEquals(
            KIND_PREFIXES.map {
                "$it:"
            }.filter { it.startsWith("b") },
            prefixSuggestions("b")
        )
        assertTrue(prefixSuggestions("").isEmpty())
        assertTrue(prefixSuggestions("design").isEmpty())
        assertTrue(prefixSuggestions("design:").isEmpty())
        assertTrue(prefixSuggestions("de sign").isEmpty())
        assertTrue(prefixSuggestions("표").isEmpty())
    }

    @Test
    fun enterWhileAnInputMethodIsComposingDoesNotSend() {
        assertNull(composerKey(enter = true, tab = false, shift = false, false, composing = true))
        assertNull(composerKey(enter = true, tab = false, shift = true, false, composing = true))
        assertNull(composerKey(enter = false, tab = true, shift = false, true, composing = true))
        assertEquals(
            ComposerKey.SEND,
            composerKey(enter = true, tab = false, shift = false, false, composing = false)
        )
    }

    @Test
    fun enterSendsShiftEnterBreaksTabCompletes() {
        assertEquals(ComposerKey.SEND, composerKey(enter = true, tab = false, shift = false, false))
        assertEquals(
            ComposerKey.NEWLINE,
            composerKey(enter = true, tab = false, shift = true, false)
        )
        assertEquals(
            ComposerKey.COMPLETE,
            composerKey(enter = false, tab = true, shift = false, true)
        )
        assertNull(composerKey(enter = false, tab = true, shift = false, hasSuggestions = false))
        assertNull(composerKey(enter = false, tab = false, shift = false, hasSuggestions = true))
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

    @Test
    fun pendingMessageFoldsEarlierConversation() {
        val page = OpenPage(detail(listOf("b01")))
            .copy(pending = listOf(PendingMessage("pending-1", "다음")))

        val folded = foldedKeys(page.flowItems, expandAll = false, toggled = emptySet())

        assertEquals(setOf("b01"), folded)
    }

    private fun detail(userBlocks: List<String>) = PageDetail(
        id = "p",
        space = "root",
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
