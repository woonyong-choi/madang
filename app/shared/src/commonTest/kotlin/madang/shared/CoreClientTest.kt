package madang.shared

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.ServerResponseException
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CoreClientTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    @Test
    fun healthHitsDefaultAddress() = runTest {
        val engine = MockEngine { request ->
            assertEquals(HttpMethod.Get, request.method)
            assertEquals("http://127.0.0.1:7470/health", request.url.toString())
            respond("""{"status":"ok","version":"0.1.0","extra":1}""", HttpStatusCode.OK, jsonHeaders)
        }
        CoreClient(engine = engine).use { client ->
            val health = client.health()
            assertTrue(health.isOk)
            assertEquals("0.1.0", health.version)
        }
    }

    @Test
    fun healthUsesCustomBaseUrl() = runTest {
        val engine = MockEngine { request ->
            assertEquals("http://192.168.0.10:7471/health", request.url.toString())
            respond("""{"status":"starting"}""", HttpStatusCode.OK, jsonHeaders)
        }
        CoreClient(baseUrl = "http://192.168.0.10:7471/", engine = engine).use { client ->
            assertFalse(client.health().isOk)
        }
    }

    @Test
    fun healthFailsOnServerError() = runTest {
        val engine = MockEngine { respond("down", HttpStatusCode.ServiceUnavailable) }
        CoreClient(engine = engine).use { client ->
            assertFailsWith<ServerResponseException> { client.health() }
        }
    }
}
