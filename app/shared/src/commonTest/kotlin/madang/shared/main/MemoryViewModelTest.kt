package madang.shared.main

import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import madang.api.client.MemoryApi
import madang.api.model.MemoryLayer
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.json

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryViewModelTest {

    private var stateContent = "---\\nstatus: review\\n---\\n## 목표\\n표\\n"
    private var saveResponse: Pair<HttpStatusCode, String>? = null

    private fun TestScope.memory(): Pair<MemoryViewModel, MockCore> {
        val mock = MockCore(this) { request ->
            val path = request.url.encodedPath
            when {
                path == "/pages/resume/memory" -> json(memoryJson())

                path == "/pages/resume/memory/state" && request.method == HttpMethod.Put -> {
                    val (status, body) = checkNotNull(saveResponse)
                    json(body, status)
                }

                else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
            }
        }
        val api = CoreClient("http://core", mock.engine).api(::MemoryApi)
        return MemoryViewModel(api, backgroundScope) to mock
    }

    private fun memoryJson() = """{
        "root":{"layer":"root","path":"root.md","content":"# 나\n","tokens":3},
        "space":{"layer":"space","path":"spaces/jobs/space.md","content":"지원\n","tokens":2},
        "state":{"layer":"state","path":"spaces/jobs/pages/resume/state.md",
          "content":"$stateContent","tokens":12,"token_limit":2000}}"""

    @Test
    fun opensWithThreeLayersAndStateSelected() = runTest {
        val (viewModel, _) = memory()

        viewModel.open("resume")
        runCurrent()

        val state = viewModel.state.value
        assertEquals(MemoryLayer.entries.toSet(), state.drafts.keys)
        assertEquals(MemoryLayer.STATE, state.layer)
        assertEquals(2000, state.current?.file?.tokenLimit)
        assertFalse(state.current!!.dirty)
    }

    @Test
    fun rejectedSaveKeepsTextAndPlacesIssuesOnLines() = runTest {
        saveResponse = HttpStatusCode.BadRequest to """{"error":"invalid",
            "message":"state.md failed validation","issues":[
            {"code":"invalid-value","message":"status: expected planning | doing","line":2,
             "path":"state.md"},
            {"code":"token-limit","message":"state.md is 2310 tokens","line":null,
             "path":"state.md"}]}"""
        val (viewModel, mock) = memory()
        viewModel.open("resume")
        runCurrent()

        viewModel.edit("---\nstatus: finished\n---\n")
        viewModel.save()
        runCurrent()

        assertTrue(
            "PUT /pages/resume/memory/state" to """{"content":"---\nstatus: finished\n---\n"}""" in
                mock.requests
        )
        val draft = viewModel.state.value.current!!
        assertEquals("---\nstatus: finished\n---\n", draft.text)
        assertTrue(draft.dirty)
        assertFalse(draft.saving)
        assertEquals(listOf(2), draft.issuesByLine.keys.toList())
        assertEquals(listOf("token-limit"), draft.fileIssues.map { it.code })
    }

    @Test
    fun savedFileReplacesTheDraftAndClearsIssues() = runTest {
        saveResponse = HttpStatusCode.BadRequest to
            """{"error":"invalid","message":"bad","issues":[]}"""
        val (viewModel, _) = memory()
        viewModel.open("resume")
        runCurrent()
        viewModel.edit("x")
        viewModel.save()
        runCurrent()
        assertEquals(listOf("invalid"), viewModel.state.value.current!!.issues.map { it.code })

        saveResponse = HttpStatusCode.OK to """{"layer":"state","path":"state.md",
            "content":"---\nstatus: doing\n---\n","tokens":8,"token_limit":2000}"""
        viewModel.edit("---\nstatus: doing\n---\n")
        viewModel.save()
        runCurrent()

        val draft = viewModel.state.value.current!!
        assertTrue(draft.saved)
        assertFalse(draft.dirty)
        assertTrue(draft.issues.isEmpty())
        assertEquals(8, draft.file.tokens)
    }

    @Test
    fun reloadKeepsLayersTheUserIsEditing() = runTest {
        val (viewModel, _) = memory()
        viewModel.open("resume")
        runCurrent()
        viewModel.edit("고치는 중")

        stateContent = "---\\nstatus: doing\\n---\\n"
        viewModel.onUpdated("resume", MemoryLayer.STATE)
        runCurrent()

        val draft = viewModel.state.value.current!!
        assertEquals("고치는 중", draft.text)
        assertEquals("---\nstatus: doing\n---\n", draft.file.content)
    }

    @Test
    fun stateOfAnotherPageIsIgnored() = runTest {
        val (viewModel, mock) = memory()
        viewModel.open("resume")
        runCurrent()

        viewModel.onUpdated("other", MemoryLayer.STATE)
        runCurrent()

        assertEquals(1, mock.requests.count { it.first == "GET /pages/resume/memory" })
    }

    @Test
    fun closeForgetsThePage() = runTest {
        val (viewModel, _) = memory()
        viewModel.open("resume")
        runCurrent()

        viewModel.close()

        assertFalse(viewModel.state.value.isOpen)
        assertNull(viewModel.state.value.current)
    }
}
