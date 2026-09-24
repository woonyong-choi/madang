package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.RunRecord
import madang.api.model.RunResultStatus
import madang.api.model.RunUsage
import madang.api.model.RunVerify

/** 기록 탭: 최근 run부터, 이유는 같은 run의 router 메시지. */
class HistoryRowTest {

    private fun run(n: Int, status: RunResultStatus) = RunRecord(
        n = n,
        usage = RunUsage(1, 0, 1),
        changedFiles = emptyList(),
        unknownFiles = emptyList(),
        verify = RunVerify(),
        resultStatus = status
    )

    @Test
    fun newestRunFirstWithItsRouterReason() {
        val page = PageDetail(
            id = "p",
            project = NOTES,
            title = "p",
            status = PageStatus.DOING,
            pinned = false,
            tags = emptyList(),
            blocks = listOf(
                BlockHeader(
                    id = "b1",
                    type = BlockType.MESSAGE,
                    role = MessageRole.USER,
                    text = "hi"
                ),
                BlockHeader(
                    id = "b2",
                    type = BlockType.MESSAGE,
                    role = MessageRole.ROUTER,
                    run = 1,
                    text = "kind=small → codex/gpt-6-luna"
                )
            ),
            runs = listOf(run(1, RunResultStatus.REVIEW), run(2, RunResultStatus.ERROR)),
            unknownFiles = emptyList()
        )

        val rows = historyRows(page)

        assertEquals(listOf(2, 1), rows.map { it.n })
        assertEquals(listOf(null, "kind=small → codex/gpt-6-luna"), rows.map { it.reason })
        assertEquals(listOf(RunGlyph.FAILED, RunGlyph.DONE), rows.map { it.glyph })
    }
}
