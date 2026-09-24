package madang.shared.core

import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.coroutines.test.runTest
import madang.api.client.ProjectsApi
import madang.api.model.Health
import madang.api.model.RoutesDocument
import madang.shared.HEALTH_JSON
import madang.shared.MockCore
import madang.shared.json

class CoreClientTest {

    @Test
    fun healthUsesGeneratedClient() = runTest {
        val mock = MockCore(this) { json(HEALTH_JSON) }
        CoreClient("http://127.0.0.1:7481/", mock.engine).use { client ->
            assertEquals(Health(Health.Status.OK, "0.1.0"), client.health())
            assertEquals("GET /health", mock.requests.single().first)
            assertEquals("http://127.0.0.1:7481", client.baseUrl)
        }
    }

    @Test
    fun apiErrorBecomesException() = runTest {
        val mock = MockCore(this) {
            json("""{"error":"not_found","message":"no projects"}""", HttpStatusCode.NotFound)
        }
        CoreClient(engine = mock.engine).use { client ->
            val error = assertFailsWith<CoreApiException> {
                client.api(::ProjectsApi).listProjects().bodyOrThrow()
            }
            assertEquals(404, error.status)
            assertEquals("not_found", error.error?.error)
        }
    }

    @Test
    fun invalidRoutesReturnIssues() = runTest {
        val mock = MockCore(this) {
            json(
                """
                {"error":"invalid","message":"routes.yaml failed validation","issues":[
                  {"code":"invalid-value","message":"default_kind: unknown kind 'x'",
                   "line":2,"path":"config/routes.yaml"}]}
                """,
                HttpStatusCode.BadRequest
            )
        }
        CoreClient(engine = mock.engine).use { client ->
            val error = assertFailsWith<CoreApiException> {
                client.setup.saveRoutes(RoutesDocument("kinds: []")).bodyOrThrow()
            }
            assertEquals(400, error.status)
            assertEquals("invalid-value", error.issues.single().code)
            assertEquals("PUT /config/routes" to """{"text":"kinds: []"}""", mock.requests.single())
        }
    }
}
