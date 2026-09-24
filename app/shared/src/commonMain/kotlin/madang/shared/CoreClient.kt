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

/** `GET /health` 응답. */
@Serializable
data class Health(val status: String, val version: String? = null) {
    val isOk: Boolean get() = status == "ok"
}

/**
 * madang-core용 HTTP 클라이언트.
 *
 * [engine]을 넘기면 전송 계층을 바꿀 수 있다(테스트는 MockEngine 사용).
 * 넘기지 않으면 플랫폼 기본 엔진을 쓴다.
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
