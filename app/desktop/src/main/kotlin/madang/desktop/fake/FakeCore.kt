package madang.desktop.fake

import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import madang.api.model.Issue
import madang.api.model.ValidationFailure
import madang.shared.core.EventTransport

/**
 * 개발용 가짜 core(`MADANG_FAKE_CORE=1`).
 *
 * 계약에 있는 경로는 계약 예시로 답한다. 설정 경로(`/home`, `/config/routes`, `/config`,
 * `/projects/{p}/config`)는 메모리 상태로 흉내 낸다. 전역 설정은 처음에 없는 상태로 시작한다([homeReady]가 거짓일 때).
 *
 * [fixture]가 있으면 프로젝트·페이지·블록 경로는 픽스처 앱 홈으로 답하고, 이벤트도 픽스처의
 * 것을 보낸다.
 */
class FakeCore(
    private val examples: ContractExamples,
    homeReady: Boolean = false,
    private val fixture: FixtureHome? = null
) {

    private var home = HomeState(path = "~/.madang", initialized = homeReady)
    private var routes = SAMPLE_ROUTES
    private val config = FakeConfig()

    val engine: HttpClientEngine = MockEngine { request -> handle(request) }

    /**
     * 연결되면 계약의 이벤트 예시를 차례로 보내고 연결을 유지한다. 픽스처가 있으면 픽스처의
     * 처음 이벤트를 보내고, 이후 바꾸는 요청에서 난 이벤트를 보낸다.
     */
    val events = EventTransport { onOpen, onFrame ->
        onOpen()
        if (fixture == null) {
            for (event in examples.events()) {
                delay(EVENT_INTERVAL)
                onFrame(event)
            }
            awaitCancellation()
        }
        fixture.initialEvents.forEach { onFrame(it) }
        fixture.events.collect { onFrame(it) }
    }

    private fun MockRequestHandleScope.handle(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath
        val body = (request.body as? TextContent)?.text
        return when {
            path == "/home" && request.method == HttpMethod.Get -> json(home.toJson())

            path == "/home" && request.method == HttpMethod.Post -> initHome(body)

            path == "/config/routes" && request.method == HttpMethod.Get -> json(routesJson())

            path == "/config/routes" && request.method == HttpMethod.Put -> saveRoutes(body)

            path == "/config" && request.method == HttpMethod.Get -> json(textJson(config.global()))

            path == "/config" && request.method == HttpMethod.Put ->
                saveConfig(body) { config.saveGlobal(it) to config.global() }

            PROJECT_CONFIG.matches(path) -> projectConfig(request.method, path, body)

            else -> fixture?.handle(request.method.value, path, body, query(request))
                ?.let { fixtureResponse(it) }
                ?: contractResponse(request.method.value, path)
        }
    }

    private fun query(request: HttpRequestData): Map<String, String> =
        request.url.parameters.names().associateWith { request.url.parameters[it].orEmpty() }

    private fun MockRequestHandleScope.fixtureResponse(
        response: FixtureResponse
    ): HttpResponseData {
        val status = HttpStatusCode.fromValue(response.status)
        return response.body?.let {
            respond(it, status, headersOf(HttpHeaders.ContentType, "application/json"))
        } ?: respond("", status)
    }

    private fun MockRequestHandleScope.contractResponse(
        method: String,
        path: String
    ): HttpResponseData {
        val example = examples.response(method, path)
            ?: return error(
                HttpStatusCode.NotFound,
                "not_found",
                "$method $path is not in the contract"
            )
        val status = HttpStatusCode.fromValue(example.status)
        return example.body?.let { json(it, status) } ?: respond("", status)
    }

    private fun MockRequestHandleScope.initHome(body: String?): HttpResponseData {
        val request = body?.let { Json.parseToJsonElement(it).jsonObject }
            ?: return error(HttpStatusCode.BadRequest, "invalid", "missing body")
        home = HomeState(
            path = request["path"]?.jsonPrimitive?.content ?: home.path,
            initialized = true
        )
        return json(home.toJson())
    }

    private fun MockRequestHandleScope.saveRoutes(body: String?): HttpResponseData {
        val text =
            body?.let { Json.parseToJsonElement(it).jsonObject["text"]?.jsonPrimitive?.content }
                ?: return error(HttpStatusCode.BadRequest, "invalid", "missing text")
        val missing = REQUIRED_ROUTE_KEYS.filter { key ->
            text.lines().none { it.startsWith("$key:") }
        }
        if (missing.isNotEmpty()) return json(validationFailure(missing), HttpStatusCode.BadRequest)
        routes = text
        return json(routesJson())
    }

    private fun routesJson() = textJson(routes)

    private fun textJson(text: String) = buildJsonObject { put("text", text) }

    private fun MockRequestHandleScope.projectConfig(
        method: HttpMethod,
        path: String,
        body: String?
    ): HttpResponseData {
        val id = checkNotNull(PROJECT_CONFIG.matchEntire(path)).groupValues[1]
        return when (method) {
            HttpMethod.Get -> json(textJson(config.project(id)))
            HttpMethod.Put -> saveConfig(body) { config.saveProject(id, it) to config.project(id) }
            else -> error(HttpStatusCode.MethodNotAllowed, "invalid", "$method $path")
        }
    }

    /** 설정 원문을 [save]로 검사해 저장한다. [save]는 문제 목록과 저장 뒤 원문을 돌려준다. */
    private fun MockRequestHandleScope.saveConfig(
        body: String?,
        save: (String) -> Pair<List<Issue>, String>
    ): HttpResponseData {
        val text =
            body?.let { Json.parseToJsonElement(it).jsonObject["text"]?.jsonPrimitive?.content }
                ?: return error(HttpStatusCode.BadRequest, "invalid", "missing text")
        val (issues, saved) = save(text)
        if (issues.isEmpty()) return json(textJson(saved))
        val failure = ValidationFailure(
            error = ValidationFailure.Error.INVALID,
            message = "config.yaml failed validation",
            issues = issues
        )
        return json(Json.encodeToJsonElement(ValidationFailure.serializer(), failure), BAD_REQUEST)
    }

    private fun validationFailure(missing: List<String>) = buildJsonObject {
        put("error", "invalid")
        put("message", "routes.yaml failed validation")
        put(
            "issues",
            buildJsonArray {
                for (key in missing) {
                    add(
                        buildJsonObject {
                            put("code", "missing-key")
                            put("message", "missing required key '$key'")
                            put("line", JsonPrimitive(null as Int?))
                            put("path", "config/routes.yaml")
                        }
                    )
                }
            }
        )
    }

    private fun MockRequestHandleScope.error(
        status: HttpStatusCode,
        code: String,
        message: String
    ) = json(
        buildJsonObject {
            put("error", code)
            put("message", message)
        },
        status
    )

    private fun MockRequestHandleScope.json(
        body: JsonElement,
        status: HttpStatusCode = HttpStatusCode.OK
    ) = respond(body.toString(), status, headersOf(HttpHeaders.ContentType, "application/json"))

    private data class HomeState(val path: String, val initialized: Boolean) {
        fun toJson(): JsonObject = buildJsonObject {
            put("path", path)
            put("initialized", initialized)
        }
    }

    private companion object {
        val EVENT_INTERVAL = 700.milliseconds
        val REQUIRED_ROUTE_KEYS = listOf("kinds", "default_kind", "tiers")
        val PROJECT_CONFIG = Regex("^/projects/([^/]+)/config$")
        val BAD_REQUEST = HttpStatusCode.BadRequest

        val SAMPLE_ROUTES = """
            kinds: [design, build, small, review, explore]
            default_kind: build
            prefix_override: true
            rules:
              design: [설계, 아키텍처, 원인, 왜, 구조]
              review: [리뷰, 검토, 점검]
              small: [오타, 이름, 한 줄, 문구]
              explore: [어디, 찾아, 설명해, 뭐야]
            tiers:
              design: [{runner: claude, model: claude-opus-5-5, effort: high}]
              build: [{runner: codex, model: gpt-6-sol, effort: medium}]
              small: [{runner: codex, model: gpt-6-luna, effort: high}]
              review: [{runner: opposite, model: primary}]
              explore: [{runner: codex, model: gpt-6-luna, effort: medium}]
        """.trimIndent() + "\n"
    }
}
