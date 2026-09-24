package madang.shared.core

import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlinx.coroutines.test.runTest
import madang.api.client.SpacesApi
import madang.api.model.Health
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
            json("""{"error":"not_found","message":"no spaces"}""", HttpStatusCode.NotFound)
        }
        CoreClient(engine = mock.engine).use { client ->
            val error = assertFailsWith<CoreApiException> {
                client.api(::SpacesApi).listSpaces().bodyOrThrow()
            }
            assertEquals(404, error.status)
            assertEquals("not_found", error.error?.error)
        }
    }

    @Test
    fun homeIsNullWhenCoreDoesNotKnowEndpoint() = runTest {
        val mock =
            MockCore(this) {
                json("""{"error":"not_found","message":"x"}""", HttpStatusCode.NotFound)
            }
        CoreClient(engine = mock.engine).use { assertNull(it.setup.home()) }
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
            val result = assertIs<RoutesSaveResult.Invalid>(client.setup.saveRoutes("kinds: []"))
            assertEquals("invalid-value", result.failure.issues.single().code)
            assertEquals("PUT /config/routes" to """{"text":"kinds: []"}""", mock.requests.single())
        }
    }
}
