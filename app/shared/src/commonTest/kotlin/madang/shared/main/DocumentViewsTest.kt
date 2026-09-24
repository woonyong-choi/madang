package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import madang.api.model.ViewerStatus
import madang.shared.LocalFiles

/** view 펜스 풀기: 등록부가 선언한 폴더와 문서 폴더의 데이터만 읽는다. */
class DocumentViewsTest {

    private val viewers = listOf(
        viewer("resume/basic", "/src/viewers/resume-basic"),
        viewer("jobs/cards", "/src/cards", ViewerStatus.Follow.PINNED, pinned = "3f2a"),
        viewer("jobs/gone", "/old/gone", status = ViewerStatus.Status.BROKEN)
    )

    private val files = MapFiles(
        mapOf(
            "/src/viewers/resume-basic/viewer.json" to
                """{"name":"resume/basic","entry":"index.html"}""",
            "/src/viewers/resume-basic/index.html" to "<p>resume</p>",
            "/home/cache/3f2a/jobs/cards/viewer.json" to """{"entry":"./view.html"}""",
            "/home/cache/3f2a/jobs/cards/view.html" to "<p>pinned</p>",
            "/docs/base.json" to """{"name": "김마당"}""",
            "/docs/list.yaml" to "name: 김마당\nyears: 3\n",
            "/docs/bad.json" to "{"
        )
    )

    private var listed = 0

    private val documentViews = DocumentViews(
        listViewers = {
            listed++
            viewers
        },
        home = { "/home" },
        files = files
    )

    @Test
    fun declaredViewersResolveWithTheirData() = runTest {
        val markdown = fences(
            "resume/basic data=./base.json",
            "jobs/cards data=list.yaml",
            "jobs/gone data=./base.json",
            "nobody/here",
            "resume/basic data=./bad.json"
        )

        val views = documentViews.resolve(markdown, "/docs", "jobs")

        val name = buildJsonObject { put("name", "김마당") }
        assertEquals(
            ViewEntry(ViewEntry.OK, html = "<p>resume</p>", data = name),
            views["resume/basic data=./base.json"]
        )
        val pinned = views.getValue("jobs/cards data=list.yaml")
        assertEquals(ViewEntry.OK, pinned.status)
        assertEquals("<p>pinned</p>", pinned.html)
        assertEquals(
            buildJsonObject {
                put("name", "김마당")
                put("years", JsonPrimitive(3))
            },
            pinned.data
        )
        assertEquals(ViewEntry.BROKEN, views.getValue("jobs/gone data=./base.json").status)
        assertEquals(name, views.getValue("jobs/gone data=./base.json").data)
        assertEquals(ViewEntry.MISSING, views.getValue("nobody/here").status)
        assertEquals(ViewEntry.INVALID, views.getValue("resume/basic data=./bad.json").status)
    }

    @Test
    fun fencePinWinsOverTheLiveSource() = runTest {
        val views = documentViews.resolve(fences("jobs/cards@3f2a"), "/docs", null)

        assertEquals("<p>pinned</p>", views.getValue("jobs/cards@3f2a").html)
    }

    @Test
    fun documentsWithoutFencesDoNotAskCore() = runTest {
        assertTrue(documentViews.resolve("# 제목\n", "/docs", "jobs").isEmpty())
        assertEquals(0, listed)
    }

    @Test
    fun unknownFolderLeavesDataInvalid() = runTest {
        val views = documentViews.resolve(fences("resume/basic data=./base.json"), null, null)

        assertEquals(ViewEntry.INVALID, views.values.single().status)
    }

    private fun fences(vararg infos: String): String =
        infos.joinToString("\n") { "```view $it\n```\n" }

    private fun viewer(
        name: String,
        source: String,
        follow: ViewerStatus.Follow = ViewerStatus.Follow.LIVE,
        pinned: String? = null,
        status: ViewerStatus.Status = ViewerStatus.Status.OK
    ) = ViewerStatus(
        name = name,
        source = source,
        follow = follow,
        status = status,
        scope = ViewerStatus.Scope.REGISTRY,
        pinned = pinned
    )

    private class MapFiles(private val contents: Map<String, String>) : LocalFiles {
        override suspend fun read(path: String): String =
            contents[path] ?: throw IllegalStateException("no such file: $path")

        override fun openExternally(target: String) = Unit
    }
}
