package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** 문서 탭과 렌더러 호스트 사이의 약속: 요청 주소, 링크 풀기, view 펜스 찾기, 넘기는 JSON. */
class DocumentModelTest {

    @Test
    fun hostRequestsAreParsed() {
        assertEquals(
            DocumentRequest.Link("./base.json"),
            parseDocumentRequest("madang-app://open?href=.%2Fbase.json")
        )
        assertEquals(
            DocumentRequest.Block("b04", "blocks/b04 cover.md"),
            parseDocumentRequest("madang-app://block?id=b04&href=blocks%2Fb04%20cover.md")
        )
        assertEquals(DocumentRequest.Run(3), parseDocumentRequest("madang-app://run?n=3"))
        assertNull(parseDocumentRequest("madang-app://run?n=x"))
        assertNull(parseDocumentRequest("madang-app://other?href=a"))
        assertNull(parseDocumentRequest("https://example.com/"))
    }

    @Test
    fun linksOpenByScheme() {
        val dir = "/work/jobs/docs"
        assertEquals(
            LinkTarget.Open(OpenRequest.File("/work/jobs/docs/base.json")),
            linkTarget("./base.json", dir)
        )
        assertEquals(
            LinkTarget.Open(OpenRequest.File("/work/jobs/data/my table.csv")),
            linkTarget("../data/my%20table.csv#top", dir)
        )
        assertEquals(
            LinkTarget.Open(OpenRequest.Url("https://example.com/a")),
            linkTarget("https://example.com/a", dir)
        )
        assertEquals(
            LinkTarget.External("mailto:me@example.com"),
            linkTarget("mailto:me@example.com", dir)
        )
        assertNull(linkTarget("javascript:alert(1)", dir))
        assertNull(linkTarget("./base.json", null))
        assertNull(linkTarget("#section", dir))
    }

    @Test
    fun pathsAreJoinedAndDecoded() {
        assertEquals("/a/c", joinPath("/a/b/", "../c"))
        assertEquals("/x/y", joinPath("/a", "/x/./y"))
        assertEquals("/a", parentPath("/a/b.md"))
        assertEquals("이력서 1.md", percentDecode("%EC%9D%B4%EB%A0%A5%EC%84%9C%201.md"))
        assertEquals("100%", percentDecode("100%"))
    }

    @Test
    fun viewFencesAreFoundOnceInOrder() {
        val markdown = """
            ---
            title: x
            ---
            ```view resume/basic data=./base.json
            ```

            ````md
            ```view inside/code
            ```
            ````

            ```view jobs/cards@3f2a data=./a.yaml data=./b.yaml
            ```

            ```view resume/basic  data=./base.json
            ```
        """.trimIndent()

        assertEquals(
            listOf(
                ViewRef("resume/basic data=./base.json", "resume/basic", null, "./base.json"),
                ViewRef(
                    "jobs/cards@3f2a data=./a.yaml data=./b.yaml",
                    "jobs/cards",
                    "3f2a",
                    "./b.yaml"
                )
            ),
            findViews(markdown)
        )
    }

    @Test
    fun payloadLeavesOutEmptyFields() {
        val payload = DocumentPayload(
            markdown = "# a",
            context = DocumentContext(
                views = mapOf("x" to ViewEntry(ViewEntry.MISSING)),
                runs = listOf(RunEntry(n = 1))
            )
        ).toJson()
        val json = Json.parseToJsonElement(payload).jsonObject

        assertEquals("# a", json["markdown"]?.jsonPrimitive?.content)
        assertNull(json["base"])
        val view = json["context"]!!.jsonObject["views"]!!.jsonObject["x"]!!.jsonObject
        assertEquals(setOf("status"), view.keys)
    }
}
