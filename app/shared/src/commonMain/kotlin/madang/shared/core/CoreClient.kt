package madang.shared.core

import io.ktor.client.HttpClient
import io.ktor.client.HttpClientConfig
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.serialization.kotlinx.json.json
import io.ktor.util.reflect.typeInfo
import kotlinx.serialization.json.Json
import madang.api.client.RunnersApi
import madang.api.client.SystemApi
import madang.api.infrastructure.HttpResponse
import madang.api.model.ApiError
import madang.api.model.Health

/**
 * madang-core 연결 하나.
 *
 * HTTP 클라이언트 하나를 만들어 생성된 API 클래스들이 함께 쓰게 한다. 화면은 [api]로
 * 필요한 생성 클라이언트(`SpacesApi`, `PagesApi` 등)를 얻는다.
 *
 * [engine]을 넘기면 전송 계층을 바꿀 수 있다(테스트와 가짜 core는 MockEngine 사용).
 */
class CoreClient(baseUrl: String = DEFAULT_BASE_URL, engine: HttpClientEngine? = null) :
    AutoCloseable {

    /** 끝의 `/`를 뗀 core 주소. */
    val baseUrl: String = baseUrl.trimEnd('/')

    val http: HttpClient =
        if (engine != null) HttpClient(engine) { configure() } else HttpClient { configure() }

    val system: SystemApi = api(::SystemApi)
    val runners: RunnersApi = api(::RunnersApi)
    val setup: CoreSetupApi = CoreSetupApi(this.baseUrl, http)

    /** 이 연결의 HTTP 클라이언트를 공유하는 생성 API 클라이언트를 만든다. */
    fun <T> api(factory: (String, HttpClient) -> T): T = factory(baseUrl, http)

    /** `GET /health`. 응답이 없거나 2xx가 아니면 예외를 던진다. */
    suspend fun health(): Health = system.getHealth().bodyOrThrow()

    override fun close() = http.close()

    private fun HttpClientConfig<*>.configure() {
        install(ContentNegotiation) { json(CoreJson) }
        install(WebSockets)
    }

    companion object {
        const val DEFAULT_BASE_URL = "http://127.0.0.1:7470"

        val CoreJson = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
        }
    }
}

/** core가 2xx가 아닌 응답을 돌려줬다. [error]는 본문이 `ApiError`일 때만 있다. */
class CoreApiException(val status: Int, val error: ApiError?) :
    RuntimeException(error?.let { "${it.error}: ${it.message}" } ?: "HTTP $status")

/** 성공 응답이면 본문을, 아니면 [CoreApiException]을 던진다. */
suspend fun <T : Any> HttpResponse<T>.bodyOrThrow(): T {
    if (success) return body()
    val error = runCatching { typedBody<ApiError>(typeInfo<ApiError>()) }
    throw CoreApiException(status, error.getOrNull())
}
