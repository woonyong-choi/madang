package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import madang.api.model.Issue

class MemoryHeaderTest {

    private val ledger = listOf(
        "---",
        "status: review",
        "tasks:",
        "  - {id: T1, title: 뷰 만들기, status: done}",
        "  - {id: T2, title: 프리셋, status: review}",
        "decisions: []  # 아직 없음",
        "---",
        "## 목표",
        "이력서 뷰"
    ).joinToString("\n")

    @Test
    fun splitsTopLevelKeysWithTheirBlocks() {
        val parts = splitMemory(ledger)

        assertTrue(parts.hasHeader)
        assertEquals(listOf("status", "tasks", "decisions"), parts.fields.map { it.key })
        assertEquals("review", parts.fields[0].value)
        assertEquals(
            "  - {id: T1, title: 뷰 만들기, status: done}\n  - {id: T2, title: 프리셋, status: review}",
            parts.fields[1].value
        )
        assertEquals(listOf(2, 3, 6), parts.fields.map { it.line })
        assertEquals(3, parts.fields[1].lineCount)
        assertEquals("## 목표\n이력서 뷰", parts.body)
        assertEquals(8, parts.bodyLine)
    }

    @Test
    fun fileWithoutHeaderIsAllBody() {
        val parts = splitMemory("# 나에 대해\n한국어로 답한다.\n")

        assertFalse(parts.hasHeader)
        assertTrue(parts.fields.isEmpty())
        assertEquals("# 나에 대해\n한국어로 답한다.\n", parts.body)
        assertEquals(1, parts.bodyLine)
    }

    @Test
    fun unchangedFieldsRoundTripExactly() {
        for (field in splitMemory(ledger).fields) {
            assertEquals(ledger, withHeaderField(ledger, field.key, field.value), field.key)
        }
    }

    @Test
    fun editingOneFieldLeavesOtherLinesAlone() {
        val edited = withHeaderField(ledger, "tasks", "  - {id: T1, title: 뷰 만들기, status: done}")

        val lines = edited.split('\n')
        assertEquals(8, lines.size)
        assertEquals("tasks:", lines[2])
        assertEquals("decisions: []  # 아직 없음", lines[4])
        assertEquals(ledger.split('\n').takeLast(3), lines.takeLast(3))
        assertEquals("status: doing", withHeaderField(ledger, "status", "doing").split('\n')[1])
    }

    @Test
    fun issuesArePlacedOnFieldsBodyOrLoose() {
        val parts = splitMemory(ledger)
        val issues = listOf(
            issue("invalid-value", 4),
            issue("missing-key", 7),
            issue("missing-section", 9),
            issue("token-limit", null)
        )

        val placed = placeIssues(parts, issues)

        assertEquals(mapOf(3 to listOf(issues[0])), placed.byField)
        assertEquals(listOf(issues[2]), placed.body)
        assertEquals(listOf(issues[1], issues[3]), placed.loose)
    }

    private fun issue(code: String, line: Int?) = Issue(code = code, message = code, line = line)
}
