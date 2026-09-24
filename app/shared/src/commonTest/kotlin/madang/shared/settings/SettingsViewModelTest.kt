package madang.shared.settings

import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import madang.shared.MockCore
import madang.shared.RUNNERS_JSON
import madang.shared.core.CoreClient
import madang.shared.json

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    private val projectConfigs = mapOf("jobs" to "track: false\\n", "blog" to "")
    private var saveProjectResponse: Pair<HttpStatusCode, String>? = null

    private fun TestScope.settings(project: String? = null): Pair<SettingsViewModel, MockCore> {
        val mock = MockCore(this) { request ->
            val path = request.url.encodedPath
            val projectConfig = PROJECT_CONFIG.matchEntire(path)
            when {
                path == "/config" -> json(text("core:\\n  port: 7470\\n"))

                path == "/config/routes" -> json(text("kinds: [build]\\n"))

                path == "/projects" -> json(PROJECTS_JSON)

                path == "/runners" -> json(RUNNERS_JSON)

                projectConfig != null && request.method == HttpMethod.Put -> {
                    val (status, body) = checkNotNull(saveProjectResponse)
                    json(body, status)
                }

                projectConfig != null ->
                    json(text(projectConfigs.getValue(projectConfig.groupValues[1])))

                else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
            }
        }
        val viewModel = SettingsViewModel(
            CoreClient("http://core", mock.engine),
            InMemorySettingsStore(),
            backgroundScope,
            onLanguageChange = {},
            onReconnect = {},
            project = project
        )
        return viewModel to mock
    }

    private fun text(value: String) = """{"text":"$value"}"""

    @Test
    fun loadsGlobalAndProjectConfigForTheGivenProject() = runTest {
        val (viewModel, _) = settings(project = "jobs")
        runCurrent()

        val state = viewModel.state.value
        assertEquals("core:\n  port: 7470\n", state.document(SettingsDocument.CONFIG).text)
        assertEquals(listOf("jobs", "blog"), state.projects.map { it.id })
        assertEquals("jobs", state.project)
        val projectConfig = state.document(SettingsDocument.PROJECT_CONFIG)
        assertEquals("track: false\n", projectConfig.text)
        assertEquals(DocumentStatus.Editing, projectConfig.status)
    }

    @Test
    fun withoutAProjectTheFirstOneIsChosen() = runTest {
        val (viewModel, _) = settings()
        runCurrent()

        assertEquals("jobs", viewModel.state.value.project)
    }

    @Test
    fun rejectedProjectConfigKeepsTextAndShowsIssuesByLine() = runTest {
        saveProjectResponse = HttpStatusCode.BadRequest to """{"error":"invalid",
            "message":"config.yaml failed validation","issues":[
            {"code":"invalid-value","message":"run: extra inputs are not permitted","line":2,
             "path":"config.yaml"}]}"""
        val (viewModel, mock) = settings(project = "jobs")
        runCurrent()

        viewModel.setText(SettingsDocument.PROJECT_CONFIG, "track: true\nrun: []\n")
        viewModel.save(SettingsDocument.PROJECT_CONFIG)
        runCurrent()

        assertTrue(
            "PUT /projects/jobs/config" to """{"text":"track: true\nrun: []\n"}""" in
                mock.requests
        )
        val editor = viewModel.state.value.document(SettingsDocument.PROJECT_CONFIG)
        assertEquals("track: true\nrun: []\n", editor.text)
        assertIs<DocumentStatus.Invalid>(editor.status)
        assertEquals(setOf(2), editor.issuesByLine.keys)
        assertTrue(editor.canSave)
    }

    @Test
    fun savedProjectConfigTakesTheCoreText() = runTest {
        saveProjectResponse = HttpStatusCode.OK to text("track: true\\n")
        val (viewModel, _) = settings(project = "jobs")
        runCurrent()

        viewModel.setText(SettingsDocument.PROJECT_CONFIG, "track: true\n")
        viewModel.save(SettingsDocument.PROJECT_CONFIG)
        runCurrent()

        val editor = viewModel.state.value.document(SettingsDocument.PROJECT_CONFIG)
        assertEquals(DocumentStatus.Saved, editor.status)
        assertEquals("track: true\n", editor.text)
    }

    @Test
    fun selectingAnotherProjectLoadsItsConfig() = runTest {
        val (viewModel, mock) = settings(project = "jobs")
        runCurrent()

        viewModel.selectProject("blog")
        runCurrent()

        assertEquals("", viewModel.state.value.document(SettingsDocument.PROJECT_CONFIG).text)
        assertTrue(mock.requests.any { it.first == "GET /projects/blog/config" })
    }

    private companion object {
        val PROJECT_CONFIG = Regex("^/projects/([^/]+)/config$")

        const val PROJECTS_JSON = """[
            {"id":"jobs","title":"지원","path":"/Users/me/jobs"},
            {"id":"blog","title":"블로그","path":"/Users/me/blog"}]"""
    }
}
