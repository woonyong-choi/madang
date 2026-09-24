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
import madang.api.model.RunTrigger
import madang.api.model.RunUsage
import madang.api.model.RunVerify
import madang.api.model.Target

/** 페이지 흐름을 렌더러에 넘길 page.md 모양 원문으로 모으기. */
class PageDocumentTest {

    private val page = PageDetail(
        id = "resume",
        project = "jobs",
        title = "이력서",
        status = PageStatus.DOING,
        pinned = false,
        tags = emptyList(),
        overview = "이력서를 다듬는다.\n",
        blocks = listOf(
            BlockHeader(
                id = "b01",
                type = BlockType.MESSAGE,
                role = MessageRole.USER,
                ts = "2026-09-24T08:11:02+09:00",
                target = Target(),
                text = "뷰 만들어줘"
            ),
            BlockHeader(
                id = "b02",
                type = BlockType.MESSAGE,
                role = MessageRole.AGENT,
                ts = "2026-09-24T08:14:40+09:00",
                run = 1,
                text = "만들었습니다."
            ),
            BlockHeader(
                id = "b03",
                type = BlockType.DOC,
                file = "blocks/b03-cover.md",
                title = "커버 레터"
            ),
            BlockHeader(id = "b04", type = BlockType.DATA, file = "blocks/b04-base.json"),
            BlockHeader(
                id = "b05",
                type = BlockType.MESSAGE,
                role = MessageRole.ROUTER,
                ts = "2026-09-24T09:00:00+09:00",
                run = 2,
                text = "테스트가 실패했습니다."
            )
        ),
        runs = listOf(run(1, "b01")),
        unknownFiles = emptyList()
    )

    private val open = OpenPage(
        page,
        contents = mapOf("b03" to "## 커버\n", "b04" to "{\"a\": 1}\n"),
        pending = listOf(PendingMessage("pending-1", "다음 요청"))
    )

    @Test
    fun flowIsBuiltFromCoreHeadersWithoutSource() {
        assertEquals(
            """
            이력서를 다듬는다.

            <!-- b01 | 2026-09-24T08:11:02+09:00 | user | target=page -->
            뷰 만들어줘

            <!-- b02 | 2026-09-24T08:14:40+09:00 | agent | run=1 -->
            만들었습니다.

            <!-- b03 |  | doc | file=blocks/b03-cover.md title=%EC%BB%A4%EB%B2%84%20%EB%A0%88%ED%84%B0 -->
            ## 커버

            <!-- b04 |  | data | file=blocks/b04-base.json -->
            ```json
            {"a": 1}
            ```

            <!-- b05 | 2026-09-24T09:00:00+09:00 | router | run=2 -->
            테스트가 실패했습니다.

            <!-- b0 |  | user | pending=true -->
            다음 요청

            """.trimIndent(),
            pageMarkdown(open, source = null)
        )
    }

    @Test
    fun sourceKeepsHeadCommentsAsWritten() {
        val source = """
            ---
            title: 이력서
            ---
            개요

            <!-- b01 | 2026-09-24T08:11:02+09:00 | user | target=page -->
            뷰 만들어줘

            <!-- b02 | 2026-09-24T08:14:40+09:00 | agent | run=1 -->
            만들었습니다.

            <!-- b05 | 2026-09-24T09:00:00+09:00 | router | run=2 ask=true options=merge,keep -->
            테스트가 실패했습니다.
        """.trimIndent() + "\n"

        val markdown = pageMarkdown(open.copy(pending = emptyList()), source)

        assertEquals(
            """
            ---
            title: 이력서
            ---
            개요

            <!-- b01 | 2026-09-24T08:11:02+09:00 | user | target=page -->
            뷰 만들어줘

            <!-- b02 | 2026-09-24T08:14:40+09:00 | agent | run=1 -->
            만들었습니다.

            <!-- b03 |  | doc | file=blocks/b03-cover.md title=%EC%BB%A4%EB%B2%84%20%EB%A0%88%ED%84%B0 -->
            ## 커버

            <!-- b04 |  | data | file=blocks/b04-base.json -->
            ```json
            {"a": 1}
            ```

            <!-- b05 | 2026-09-24T09:00:00+09:00 | router | run=2 ask=true options=merge,keep -->
            테스트가 실패했습니다.

            """.trimIndent(),
            markdown
        )
    }

    @Test
    fun onlyKeepsTheChosenBlocks() {
        val markdown = pageMarkdown(open, source = null) { it.run == 1 || it.id == "b01" }

        assertEquals(
            """
            <!-- b01 | 2026-09-24T08:11:02+09:00 | user | target=page -->
            뷰 만들어줘

            <!-- b02 | 2026-09-24T08:14:40+09:00 | agent | run=1 -->
            만들었습니다.

            """.trimIndent(),
            markdown
        )
    }

    @Test
    fun runsFollowTheirTrigger() {
        val runs = pageRuns(page.runs + run(2, null)) { "run ${it.n}" }

        assertEquals(
            listOf(
                RunEntry(1, "b01", "claude/opus", "run 1", "done", listOf("a.md")),
                RunEntry(2, null, "claude/opus", "run 2", "done", listOf("a.md"))
            ),
            runs
        )
    }

    @Test
    fun pageFileLivesInTheProjectPagesFolder() {
        assertEquals("/work/jobs/.madang/pages/resume", pageFolder("/work/jobs/", "resume"))
        assertEquals(
            "/work/jobs/.madang/pages/resume/page.md",
            pageFile(pageFolder("/work/jobs", "resume"))
        )
    }

    private fun run(n: Int, trigger: String?) = RunRecord(
        n = n,
        usage = RunUsage(input = 1, cached = 0, output = 1),
        changedFiles = listOf("a.md"),
        unknownFiles = emptyList(),
        verify = RunVerify(),
        trigger = trigger?.let { RunTrigger(message = it) },
        runner = "claude",
        model = "opus",
        resultStatus = RunResultStatus.DONE
    )
}
