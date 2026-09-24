package madang.desktop

import java.io.File
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 문서 탭 렌더러: jar에 실은 파일이 게시와 같은 `templates/_runtime`이고, 호스트 주소를 나눈다. */
class DocumentRuntimeTest {

    private val templates = File(
        checkNotNull(System.getProperty("madang.openapiSpec")) { "madang.openapiSpec is not set" }
    ).absoluteFile.parentFile.resolveSibling("templates/_runtime")

    @Test
    fun installCopiesTheSameRendererFiles() {
        val dir = Files.createTempDirectory("madang-runtime").toFile()
        try {
            val host = DocumentRuntime(dir).install()

            assertEquals(dir.resolve("app.html"), host)
            for (name in DocumentRuntime.FILES) {
                assertContentEquals(
                    templates.resolve(name).readBytes(),
                    dir.resolve(name).readBytes(),
                    name
                )
            }
            val stale = dir.resolve("document.js")
            stale.writeText("stale")
            DocumentRuntime(dir).install()
            assertTrue(stale.readText().contains("renderDocument"))
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun hostUrlsCarryTheDocumentNumber() {
        val url = DocumentBridge.hostUrl("file:///tmp/runtime/app.html", 7)

        assertEquals("file:///tmp/runtime/app.html?doc=7", url)
        assertEquals(7, DocumentBridge.documentNumber(url))
        assertNull(DocumentBridge.documentNumber("https://example.com/app.html"))
        assertNull(DocumentBridge.documentNumber("madang-app://open?href=a"))
    }
}
