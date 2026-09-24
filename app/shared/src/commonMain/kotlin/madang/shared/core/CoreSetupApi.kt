package madang.shared.core

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import madang.api.model.ApiError
import madang.api.model.ValidationFailure

/** 앱 홈 상태. [initialized]가 거짓이면 앱은 온보딩을 보여 준다. */
@Serializable
data class HomeStatus(val path: String, val initialized: Boolean, val remote: String? = null)

/** 앱 홈 초기화 요청. [remote]는 주소만 기록하며 core가 저장소를 만들지는 않는다. */
@Serializable
data class HomeInit(val path: String, val remote: String? = null)

/** `config/routes.yaml` 원문. */
@Serializable
data class RoutesDocument(val text: String)

/** routes.yaml 저장 결과. */
sealed interface RoutesSaveResult {
    data object Saved : RoutesSaveResult

    /** core 검사기가 거부했다. 파일은 바뀌지 않았다. */
    data class Invalid(val failure: ValidationFailure) : RoutesSaveResult
}

/**
 * 계약 파일(core/openapi.yaml)에 아직 없는 설정용 엔드포인트.
 *
 * 앱은 앱 홈 파일을 직접 읽거나 쓰지 않으므로 온보딩과 라우팅 표 편집도 core를 거친다.
 * 계약에 이 엔드포인트가 추가되면 생성 클라이언트로 바꾸고 이 파일을 지운다.
 *
 * - `GET /home` → [HomeStatus]
 * - `POST /home` [HomeInit] → [HomeStatus]
 * - `GET /config/routes` → [RoutesDocument]
 * - `PUT /config/routes` [RoutesDocument] → 200 [RoutesDocument] 또는 400 `ValidationFailure`
 */
class CoreSetupApi(private val baseUrl: String, private val http: HttpClient) {

    /** 앱 홈 상태. core가 이 엔드포인트를 모르면(404) null. */
    suspend fun home(): HomeStatus? {
        val response = http.get("$baseUrl/home")
        if (response.status == HttpStatusCode.NotFound) return null
        return response.successBody()
    }

    suspend fun initHome(request: HomeInit): HomeStatus = http.post("$baseUrl/home") {
        contentType(ContentType.Application.Json)
        setBody(request)
    }.successBody()

    suspend fun routes(): RoutesDocument = http.get("$baseUrl/config/routes").successBody()

    suspend fun saveRoutes(text: String): RoutesSaveResult {
        val response = http.put("$baseUrl/config/routes") {
            contentType(ContentType.Application.Json)
            setBody(RoutesDocument(text))
        }
        if (response.status == HttpStatusCode.BadRequest) {
            return RoutesSaveResult.Invalid(response.body())
        }
        response.successBody<RoutesDocument>()
        return RoutesSaveResult.Saved
    }

    private suspend inline fun <reified T> HttpResponse.successBody(): T {
        if (status.isSuccess()) return body()
        throw CoreApiException(status.value, runCatching { body<ApiError>() }.getOrNull())
    }
}
