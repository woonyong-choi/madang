package madang.shared.main

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/**
 * 문서 탭이 렌더러 호스트(`templates/_runtime/app.html`)의 `madangApp.render()`에 넘기는 것.
 * 그리는 일은 렌더러가 한다. 앱은 원문과 context만 모은다.
 *
 * @property markdown 문서 원문. 페이지 흐름이면 page.md 모양이다.
 * @property base 문서 폴더의 `file://` URL(끝 `/` 포함). 상대 경로 이미지가 여기서 풀린다.
 * @property follow 블록이 늘면 끝으로 스크롤한다(페이지 흐름).
 */
@Serializable
data class DocumentPayload(
    val markdown: String,
    val context: DocumentContext = DocumentContext(),
    val base: String? = null,
    val follow: Boolean = false
) {
    /** 호스트에 넘길 JSON. JavaScript 식으로도 그대로 쓸 수 있다. */
    fun toJson(): String = PAYLOAD_JSON.encodeToString(serializer(), this)
}

/** 렌더러 `renderDocument(markdown, context)`의 context. */
@Serializable
data class DocumentContext(
    val views: Map<String, ViewEntry> = emptyMap(),
    val tokens: AppTokens? = null,
    val runs: List<RunEntry> = emptyList()
)

/**
 * view 펜스 하나를 어떻게 그릴지. [status]가 `ok`면 [html]을 sandbox iframe에 넣고, 아니면
 * [message]와 [data] 표로 대신한다.
 */
@Serializable
data class ViewEntry(
    val status: String,
    val html: String? = null,
    val data: JsonElement? = null,
    val message: String? = null
) {
    companion object {
        const val OK = "ok"
        const val INVALID = "invalid"
        const val BROKEN = "broken"
        const val MISSING = "missing"
    }
}

/** 뷰어 iframe과 문서 바탕에 주는 앱 토큰 다섯 개(`--app-*`). */
@Serializable
data class AppTokens(
    val bg: String,
    val text: String,
    val accent: String,
    val font: String,
    val radius: String
)

/** 렌더러가 [after] 블록 뒤에 접힌 실행 블록으로 그리는 실행 기록. */
@Serializable
data class RunEntry(
    val n: Int,
    val after: String? = null,
    val title: String? = null,
    val summary: String? = null,
    val status: String? = null,
    val files: List<String> = emptyList()
)

/** 문서 안 링크를 눌러 호스트가 보낸 요청(`madang-app://<type>?<필드>`). */
sealed interface DocumentRequest {
    /** 일반 링크나 view 펜스의 "데이터" 링크. [href]는 문서에 적힌 그대로다. */
    data class Link(val href: String) : DocumentRequest

    /** 블록의 "열기". 블록이 페이지에 없으면 [href]를 링크로 연다. */
    data class Block(val id: String, val href: String) : DocumentRequest

    /** 실행 블록의 "열기". */
    data class Run(val n: Int) : DocumentRequest
}

/** 호스트가 탐색한 주소를 요청으로. 이 앱의 주소가 아니거나 필드가 모자라면 null. */
fun parseDocumentRequest(url: String): DocumentRequest? {
    if (!url.startsWith(DOCUMENT_SCHEME)) return null
    val rest = url.removePrefix(DOCUMENT_SCHEME)
    val type = rest.substringBefore('?').trimEnd('/')
    val fields = rest.substringAfter('?', "").split('&').filter { it.isNotEmpty() }.associate {
        percentDecode(it.substringBefore('=')) to percentDecode(it.substringAfter('=', ""))
    }
    return when (type) {
        "open" -> fields["href"]?.let(DocumentRequest::Link)
        "block" -> fields["id"]?.let { DocumentRequest.Block(it, fields["href"].orEmpty()) }
        "run" -> fields["n"]?.toIntOrNull()?.let(DocumentRequest::Run)
        else -> null
    }
}

/** 문서 링크가 여는 것. */
sealed interface LinkTarget {
    /** 앱 탭으로 연다. */
    data class Open(val request: OpenRequest) : LinkTarget

    /** 운영체제에 맡긴다(`mailto:`). */
    data class External(val target: String) : LinkTarget
}

/**
 * 문서 링크를 여는 방법. `http`·`https`는 브라우저 탭, `mailto`는 운영체제, 상대 경로는 [documentDir]
 * 기준 파일(확장자가 탭 종류를 정한다). 그 밖이거나 문서 폴더를 모르면 null.
 */
fun linkTarget(href: String, documentDir: String?): LinkTarget? {
    val scheme = URL_SCHEME.find(href)?.groupValues?.get(1)?.lowercase()
    return when {
        scheme == "http" || scheme == "https" -> LinkTarget.Open(OpenRequest.Url(href))

        scheme == "mailto" -> LinkTarget.External(href)

        scheme != null || href.startsWith("//") || documentDir == null -> null

        else -> {
            val path = percentDecode(href.substringBefore('#').substringBefore('?'))
            if (path.isEmpty()) {
                null
            } else {
                LinkTarget.Open(
                    OpenRequest.File(joinPath(documentDir, path))
                )
            }
        }
    }
}

/** 폴더와 상대 경로를 합치고 `.`·`..`을 푼다. 절대 경로면 그대로 푼다. */
fun joinPath(dir: String, relative: String): String {
    val start = if (relative.startsWith('/')) relative else dir.trimEnd('/') + "/" + relative
    val parts = ArrayDeque<String>()
    for (part in start.split('/')) {
        when (part) {
            "", "." -> Unit
            ".." -> parts.removeLastOrNull()
            else -> parts.addLast(part)
        }
    }
    return "/" + parts.joinToString("/")
}

/** 경로의 폴더 부분. */
fun parentPath(path: String): String = path.substringBeforeLast('/', "").ifEmpty { "/" }

/** `%XX`를 UTF-8로 푼다. 틀린 `%`는 그대로 둔다. */
fun percentDecode(text: String): String {
    if ('%' !in text) return text
    val bytes = mutableListOf<Byte>()
    var i = 0
    while (i < text.length) {
        val hex = if (text[i] == '%' && i + 3 <= text.length) text.substring(i + 1, i + 3) else ""
        if (hex.length == 2 && hex.all(::isHexDigit)) {
            bytes += hex.toInt(HEX_RADIX).toByte()
            i += 3
        } else {
            bytes += text[i].toString().encodeToByteArray().toList()
            i++
        }
    }
    return bytes.toByteArray().decodeToString()
}

private fun isHexDigit(c: Char): Boolean = c in '0'..'9' || c.lowercaseChar() in 'a'..'f'

/** 문서의 view 펜스 참조. `key`가 렌더러 `context.views`의 키다. */
data class ViewRef(val key: String, val name: String, val pin: String?, val data: String?)

/**
 * 문서의 view 펜스(` ```view <이름>[@해시] data=<경로> `)를 순서대로 찾는다. 같은 참조는 한 번만
 * 담는다. 렌더러 `listViews()`와 core `find_views()`와 같은 규칙이다.
 */
fun findViews(markdown: String): List<ViewRef> {
    val body =
        FRONT_MATTER.find(markdown)?.let { markdown.substring(it.range.last + 1) } ?: markdown
    val found = linkedMapOf<String, ViewRef>()
    var fence: String? = null
    for (line in body.lines()) {
        val match = FENCE.matchEntire(line)
        val open = fence
        if (open == null) {
            if (match == null) continue
            fence = match.groupValues[1]
            parseViewInfo(match.groupValues[2])?.let { found.getOrPut(it.key) { it } }
        } else if (match != null && closes(match, open)) {
            fence = null
        }
    }
    return found.values.toList()
}

private fun closes(match: MatchResult, open: String): Boolean {
    val marker = match.groupValues[1]
    return marker[0] == open[0] && marker.length >= open.length && match.groupValues[2].isBlank()
}

private fun parseViewInfo(info: String): ViewRef? {
    val words = info.trim().split(WHITESPACE).filter { it.isNotEmpty() }
    if (words.firstOrNull() != VIEW_LANG) return null
    val target = words.getOrElse(1) { "" }
    val data = words.drop(2).lastOrNull { it.startsWith(DATA_PREFIX) }?.removePrefix(DATA_PREFIX)
    return ViewRef(
        key = words.drop(1).joinToString(" "),
        name = target.substringBefore('@'),
        pin = target.substringAfter('@', "").ifEmpty { null },
        data = data
    )
}

/** 렌더러 호스트가 앱에 요청을 보낼 때 쓰는 주소 앞부분. */
const val DOCUMENT_SCHEME = "madang-app://"

private const val VIEW_LANG = "view"
private const val DATA_PREFIX = "data="
private const val HEX_RADIX = 16
private val URL_SCHEME = Regex("^([a-zA-Z][a-zA-Z0-9+.-]*):")
private val FRONT_MATTER = Regex("^---[ \\t]*\\r?\\n[\\s\\S]*?\\r?\\n---[ \\t]*(?:\\r?\\n|$)")
private val FENCE = Regex(" {0,3}(`{3,}|~{3,})(.*)")
private val WHITESPACE = Regex("\\s+")
private val PAYLOAD_JSON = Json { explicitNulls = false }
