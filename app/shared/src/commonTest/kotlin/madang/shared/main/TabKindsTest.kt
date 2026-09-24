package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import madang.api.model.BlockHeader
import madang.api.model.BlockType

class TabKindsTest {

    /** 탭 종류 결정 규칙 표. 요청(선언)과 확장자(사실)만 본다. */
    private val rules: List<Pair<OpenRequest, TabKind>> = listOf(
        OpenRequest.File("notes/plan.md") to TabKind.DOCUMENT,
        OpenRequest.File("README.MD") to TabKind.DOCUMENT,
        OpenRequest.File("blocks/b04-resume.view.md") to TabKind.DOCUMENT,
        OpenRequest.File("data/base.json") to TabKind.DATA,
        OpenRequest.File(".madang/config.yaml") to TabKind.DATA,
        OpenRequest.File(".github/workflows/ci.yml") to TabKind.DATA,
        OpenRequest.File("incidents.csv") to TabKind.DATA,
        OpenRequest.File("resume/site/index.html") to TabKind.BROWSER,
        OpenRequest.Url("http://localhost:5173") to TabKind.BROWSER,
        OpenRequest.Url("file:///Users/me/site/index.html") to TabKind.BROWSER,
        OpenRequest.Diff to TabKind.DIFF,
        OpenRequest.Terminal to TabKind.TERMINAL,
        OpenRequest.Chat to TabKind.CHAT,
        OpenRequest.File("src/session/lock.ts") to TabKind.DOCUMENT,
        OpenRequest.File("Makefile") to TabKind.DOCUMENT,
        OpenRequest.File(".gitignore") to TabKind.DOCUMENT,
        OpenRequest.File("page.htm") to TabKind.DOCUMENT,
        OpenRequest.File("runs/1.jsonl") to TabKind.DOCUMENT
    )

    @Test
    fun theRuleTableDecidesTheKind() {
        for ((request, kind) in rules) assertEquals(kind, tabKindOf(request), "$request")
    }

    @Test
    fun thereAreExactlySixKinds() {
        assertEquals(
            listOf("DOCUMENT", "TERMINAL", "CHAT", "BROWSER", "DIFF", "DATA"),
            TabKind.entries.map { it.name }
        )
        assertEquals(TabKind.entries.toSet(), rules.map { it.second }.toSet())
    }

    @Test
    fun filesOutsideTheTableAreTheDocumentCodeView() {
        assertTrue(isCodeView("src/session/lock.ts"))
        assertTrue(isCodeView("Makefile"))
        assertTrue(isCodeView(".gitignore"))
        assertFalse(isCodeView("notes/plan.md"))
        assertFalse(isCodeView("base.json"))
        assertFalse(isCodeView("index.html"))
    }

    @Test
    fun extensionIsTheLastDotOfTheFileName() {
        assertEquals("md", extensionOf("a/b.view.md"))
        assertEquals("json", extensionOf("C:\\data\\Base.JSON"))
        assertEquals("", extensionOf(".env"))
        assertEquals("", extensionOf("dir.d/Makefile"))
        assertEquals("", extensionOf("trailing."))
    }

    @Test
    fun blocksOpenWhatTheirHeaderDeclares() {
        fun block(
            type: BlockType,
            file: String? = null,
            path: String? = null,
            url: String? = null
        ) = BlockHeader(id = "b01", type = type, file = file, path = path, url = url)

        assertNull(openRequestFor(block(BlockType.MESSAGE)))
        assertEquals(
            OpenRequest.Url("http://localhost:5173"),
            openRequestFor(
                block(BlockType.SITE, "blocks/b01.site.yaml", url = "http://localhost:5173")
            )
        )
        assertEquals(
            OpenRequest.Terminal,
            openRequestFor(block(BlockType.TERM, "blocks/b01.term.yaml"))
        )
        assertEquals(
            OpenRequest.File("src/lock.ts"),
            openRequestFor(block(BlockType.CODE, "blocks/b01.code.yaml", path = "src/lock.ts"))
        )
        assertEquals(
            OpenRequest.File("blocks/b01-base.json"),
            openRequestFor(block(BlockType.DATA, "blocks/b01-base.json"))
        )
    }

    @Test
    fun localFilesBecomeEncodedFileUrls() {
        assertEquals(
            "file:///Users/me/my%20site/index.html",
            fileUrl("/Users/me/my site/index.html")
        )
        assertEquals("file:///C:/site/%EC%9D%B4%EB%A0%A5.html", fileUrl("C:\\site\\이력.html"))
    }
}
