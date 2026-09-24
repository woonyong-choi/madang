package madang.shared.main

import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
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

    private var ledgerContent = "---\\nstatus: review\\n---\\n## 목표\\n표\\n"
    private var saveResponse: Pair<HttpStatusCode, String>? = null

    private fun TestScope.memory(): Pair<MemoryViewModel, MockCore> {
        val mock = MockCore(this) { request ->
            val path = request.url.encodedPath
            when {
                path == "/pages/resume/memory" -> json(memoryJson())

                path == "/pages/resume/memory/ledger" && request.method == HttpMethod.Put -> {
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
        "profile":{"layer":"profile","path":"profile.md","content":"# 나\n","tokens":3},
        "brief":{"layer":"brief","path":"projects/jobs/brief.md","content":"지원\n","tokens":2},
        "ledger":{"layer":"ledger","path":"projects/jobs/pages/resume/ledger.md",
          "content":"$ledgerContent","tokens":12,"token_limit":2000}}"""

    private val MemoryState.ledger: MemoryDraft get() = checkNotNull(drafts[MemoryLayer.LEDGER])

    @Test
    fun opensWithThreeLayersInProfileBriefLedgerOrder() = runTest {
        val (viewModel, _) = memory()

        viewModel.open("resume")
        runCurrent()

        val state = viewModel.state.value
        assertEquals(MEMORY_ORDER, state.ordered.map { it.file.layer })
        assertEquals(2000, state.ledger.file.tokenLimit)
        assertFalse(state.ledger.dirty)
    }

    @Test
    fun rejectedSaveKeepsTextAndPlacesIssuesOnLines() = runTest {
        saveResponse = HttpStatusCode.BadRequest to """{"error":"invalid",
            "message":"ledger.md failed validation","issues":[
            {"code":"invalid-value","message":"status: expected planning | doing","line":2,
             "path":"ledger.md"},
            {"code":"token-limit","message":"ledger.md is 2310 tokens","line":null,
             "path":"ledger.md"}]}"""
        val (viewModel, mock) = memory()
        viewModel.open("resume")
        runCurrent()

        viewModel.edit(MemoryLayer.LEDGER, "---\nstatus: finished\n---\n")
        viewModel.save(MemoryLayer.LEDGER)
        runCurrent()

        assertTrue(
            "PUT /pages/resume/memory/ledger" to """{"content":"---\nstatus: finished\n---\n"}""" in
                mock.requests
        )
        val draft = viewModel.state.value.ledger
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
        viewModel.edit(MemoryLayer.LEDGER, "x")
        viewModel.save(MemoryLayer.LEDGER)
        runCurrent()
        assertEquals(listOf("invalid"), viewModel.state.value.ledger.issues.map { it.code })

        saveResponse = HttpStatusCode.OK to """{"layer":"ledger","path":"ledger.md",
            "content":"---\nstatus: doing\n---\n","tokens":8,"token_limit":2000}"""
        viewModel.edit(MemoryLayer.LEDGER, "---\nstatus: doing\n---\n")
        viewModel.save(MemoryLayer.LEDGER)
        runCurrent()

        val draft = viewModel.state.value.ledger
        assertTrue(draft.saved)
        assertFalse(draft.dirty)
        assertTrue(draft.issues.isEmpty())
        assertEquals(8, draft.file.tokens)
    }

    @Test
    fun fieldEditRewritesOnlyThatHeaderLine() = runTest {
        val (viewModel, _) = memory()
        viewModel.open("resume")
        runCurrent()

        viewModel.editField(MemoryLayer.LEDGER, "status", "doing")

        assertEquals("---\nstatus: doing\n---\n## 목표\n표\n", viewModel.state.value.ledger.text)
    }

    @Test
    fun rawToggleIsPerLayerAndSurvivesPageChanges() = runTest {
        val (viewModel, _) = memory()
        viewModel.open("resume")

        viewModel.toggleRaw(MemoryLayer.BRIEF)
        viewModel.open("other")

        assertEquals(setOf(MemoryLayer.BRIEF), viewModel.state.value.raw)
        viewModel.toggleRaw(MemoryLayer.BRIEF)
        assertTrue(viewModel.state.value.raw.isEmpty())
    }

    @Test
    fun reloadKeepsLayersTheUserIsEditing() = runTest {
        val (viewModel, _) = memory()
        viewModel.open("resume")
        runCurrent()
        viewModel.edit(MemoryLayer.LEDGER, "고치는 중")

        ledgerContent = "---\\nstatus: doing\\n---\\n"
        viewModel.onUpdated("resume", MemoryLayer.LEDGER)
        runCurrent()

        val draft = viewModel.state.value.ledger
        assertEquals("고치는 중", draft.text)
        assertEquals("---\nstatus: doing\n---\n", draft.file.content)
    }

    @Test
    fun ledgerOfAnotherPageIsIgnored() = runTest {
        val (viewModel, mock) = memory()
        viewModel.open("resume")
        runCurrent()

        viewModel.onUpdated("other", MemoryLayer.LEDGER)
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
        assertTrue(viewModel.state.value.ordered.isEmpty())
    }
}
