package madang.shared.core

import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import madang.api.infrastructure.HttpResponse
import madang.api.infrastructure.wrap
import madang.api.model.UnknownFile
import madang.api.model.UnknownFileAction

/**
 * `POST /pages/{page}/unknown-files/{path}`. 남은 미등록 파일을 돌려준다.
 *
 * 계약은 파일 경로 전체를 퍼센트 인코딩한 한 세그먼트(`blocks%2Fnotes.txt`)로 받는다. 생성
 * 클라이언트는 `/`로 세그먼트를 나누거나 `%`를 다시 인코딩하므로 이 요청만 직접 만든다.
 */
suspend fun CoreClient.resolveUnknownFile(
    page: String,
    path: String,
    action: UnknownFileAction
): List<UnknownFile> {
    val url = "$baseUrl/pages/${encodePathSegment(page)}/unknown-files/${encodePathSegment(path)}"
    val response = http.post(url) {
        contentType(ContentType.Application.Json)
        setBody(action)
    }
    val wrapped: HttpResponse<List<UnknownFile>> = response.wrap()
    return wrapped.bodyOrThrow()
}

/** 문자열을 URL 경로 한 세그먼트로 퍼센트 인코딩한다. `/`와 `:`도 인코딩한다. */
fun encodePathSegment(value: String): String = value.encodeToByteArray().joinToString("") { byte ->
    val char = byte.toInt().toChar()
    if (byte >= 0 && (char.isLetterOrDigit() || char in UNRESERVED)) {
        char.toString()
    } else {
        "%" + (byte.toInt() and 0xFF).toString(16).uppercase().padStart(2, '0')
    }
}

private const val UNRESERVED = "-._~"
