package madang.desktop.fake

import io.ktor.client.request.get
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonArray
import madang.api.client.PagesApi
import madang.api.client.ProjectsApi
import madang.api.model.HomeInit
import madang.api.model.RoutesDocument
import madang.shared.core.CoreApiException
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow
import madang.shared.core.decodeEvent

class FakeCoreTest {

    private val examples =
        ContractExamples.load(File(checkNotNull(System.getProperty("madang.openapiSpec"))))

    private fun client(fake: FakeCore = FakeCore(examples)) =
        CoreClient(CoreClient.DEFAULT_BASE_URL, fake.engine)

    @Test
    fun contractExamplesResolveRefsAndArrays() {
        val health = assertNotNull(examples.response("GET", "/health"))
        assertEquals(200, health.status)
        assertEquals("""{"status":"ok","version":"0.1.0"}""", health.body.toString())

        val projects = assertNotNull(examples.response("GET", "/projects"))
        assertIs<JsonArray>(projects.body)

        assertNull(examples.response("GET", "/nowhere"))
    }

    @Test
    fun everyEventExampleDecodes() {
        val events = examples.events()

        assertEquals(19, events.size)
        assertTrue(events.all { decodeEvent(it) != null })
    }

    @Test
    fun servesGeneratedClientsFromExamples() = runTest {
        client().use { core ->
            assertEquals("0.1.0", core.health().version)
            assertTrue(core.api(::ProjectsApi).listProjects().bodyOrThrow().isNotEmpty())
            val page = core.api(::PagesApi).getPage("2026-09-24-resume").bodyOrThrow()
            assertEquals("2026-09-24-resume", page.id)
            assertEquals(2, core.runners.listRunners().bodyOrThrow().runners.size)
        }
    }

    @Test
    fun unknownPathIsNotFound() = runTest {
        client().use { core ->
            assertEquals(404, core.http.get("${core.baseUrl}/nowhere").status.value)
        }
    }

    @Test
    fun homeStartsMissingUntilInitialized() = runTest {
        client().use { core ->
            assertFalse(core.setup.getHome().bodyOrThrow().initialized)

            core.setup.initHome(HomeInit("~/work/madang")).bodyOrThrow()

            val home = core.setup.getHome().bodyOrThrow()
            assertTrue(home.initialized)
            assertEquals("~/work/madang", home.path)
        }
    }

    @Test
    fun routesAreCheckedBeforeSaving() = runTest {
        client().use { core ->
            val original = core.setup.getRoutes().bodyOrThrow().text

            val invalid = assertFailsWith<CoreApiException> {
                core.setup.saveRoutes(RoutesDocument("kinds: [build]\n")).bodyOrThrow()
            }
            assertEquals(listOf("missing-key", "missing-key"), invalid.issues.map { it.code })
            assertEquals(original, core.setup.getRoutes().bodyOrThrow().text)

            val edited = original.replace("default_kind: build", "default_kind: small")
            assertEquals(edited, core.setup.saveRoutes(RoutesDocument(edited)).bodyOrThrow().text)
            assertEquals(edited, core.setup.getRoutes().bodyOrThrow().text)
        }
    }
}
