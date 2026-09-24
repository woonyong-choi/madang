package madang.desktop.fake

import io.ktor.client.request.get
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonArray
import madang.api.client.PagesApi
import madang.api.client.SpacesApi
import madang.shared.core.CoreClient
import madang.shared.core.HomeInit
import madang.shared.core.RoutesSaveResult
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

        val spaces = assertNotNull(examples.response("GET", "/spaces"))
        assertIs<JsonArray>(spaces.body)

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
            assertTrue(core.api(::SpacesApi).listSpaces().bodyOrThrow().isNotEmpty())
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
            assertFalse(assertNotNull(core.setup.home()).initialized)

            core.setup.initHome(HomeInit("~/work/madang", "git@github.com:me/home.git"))

            val home = assertNotNull(core.setup.home())
            assertTrue(home.initialized)
            assertEquals("~/work/madang", home.path)
        }
    }

    @Test
    fun routesAreCheckedBeforeSaving() = runTest {
        client().use { core ->
            val original = core.setup.routes().text

            val invalid = core.setup.saveRoutes("kinds: [build]\n")
            val issues = assertIs<RoutesSaveResult.Invalid>(invalid).failure.issues
            assertEquals(listOf("missing-key", "missing-key"), issues.map { it.code })
            assertEquals(original, core.setup.routes().text)

            val edited = original.replace("default_kind: build", "default_kind: small")
            assertEquals(RoutesSaveResult.Saved, core.setup.saveRoutes(edited))
            assertEquals(edited, core.setup.routes().text)
        }
    }
}
