package madang.shared

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope

/**
 * 테스트용 가짜 core 응답. 요청 본문을 [requests]에 남긴다.
 *
 * [dispatcher]가 테스트 디스패처면 `advanceUntilIdle()`이 응답까지 기다린다.
 */
class MockCore(
    dispatcher: CoroutineDispatcher,
    private val handler: MockRequestHandleScope.(HttpRequestData) -> HttpResponseData
) {
    val requests = mutableListOf<Pair<String, String?>>()

    val engine = MockEngine(
        MockEngineConfig().apply {
            this.dispatcher = dispatcher
            addHandler { request ->
                requests += "${request.method.value} ${request.url.encodedPath}" to
                    (request.body as? TextContent)?.text
                handler(request)
            }
        }
    )
}

/** 테스트 스케줄러에서 도는 [MockCore]. */
fun MockCore(
    scope: TestScope,
    handler: MockRequestHandleScope.(HttpRequestData) -> HttpResponseData
) = MockCore(StandardTestDispatcher(scope.testScheduler), handler)

private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

fun MockRequestHandleScope.json(body: String, status: HttpStatusCode = HttpStatusCode.OK) =
    respond(body, status, jsonHeaders)

const val HEALTH_JSON = """{"status":"ok","version":"0.1.0"}"""

const val RUNNERS_JSON = """
    {"checked":"2026-09-24T09:30:12+09:00","runners":[
      {"name":"claude","available":true,"auth":"subscription","reason":null},
      {"name":"codex","available":false,"auth":"subscription","reason":"not logged in"}]}
"""
