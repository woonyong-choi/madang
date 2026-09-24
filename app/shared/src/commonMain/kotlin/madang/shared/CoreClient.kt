package madang.shared

import io.ktor.client.HttpClient
import io.ktor.client.HttpClientConfig
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.expectSuccess
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.request.get
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Response of `GET /health`. */
@Serializable
data class Health(val status: String, val version: String? = null) {
    val isOk: Boolean get() = status == "ok"
}

/**
 * HTTP client for madang-core.
 *
 * Pass [engine] to swap the transport (tests use MockEngine); otherwise the
 * platform default engine is used.
 */
class CoreClient(val baseUrl: String = DEFAULT_BASE_URL, engine: HttpClientEngine? = null) :
    AutoCloseable {

    private val http: HttpClient =
        if (engine != null) HttpClient(engine) { configure() } else HttpClient { configure() }

    private fun HttpClientConfig<*>.configure() {
        expectSuccess = true
        install(ContentNegotiation) { json(CoreJson) }
        install(WebSockets)
        defaultRequest { url(baseUrl.trimEnd('/') + "/") }
    }

    suspend fun health(): Health = http.get("health").body()

    override fun close() = http.close()

    companion object {
        const val DEFAULT_BASE_URL = "http://127.0.0.1:7470"

        val CoreJson = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
        }
    }
}
