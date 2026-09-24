package madang.shared.main

import madang.api.model.BlockHeader
import madang.api.model.BlockType

/** 가운데 탭의 여섯 종류. 무엇을 열어도 이 중 하나다. 터미널과 채팅은 자리만 있다. */
enum class TabKind { DOCUMENT, TERMINAL, CHAT, BROWSER, DIFF, DATA }

/**
 * 열기 요청. 탭 종류는 요청(선언)과 파일 확장자(사실)로만 정한다. 파일 내용을 보고 정하지 않는다.
 */
sealed interface OpenRequest {
    /** 파일 하나. 확장자가 탭 종류를 정한다. */
    data class File(val path: String) : OpenRequest

    /** URL(`http`, `https`, `file`). */
    data class Url(val url: String) : OpenRequest

    /** 페이지 작업 폴더의 git diff. */
    data object Diff : OpenRequest

    /** core PTY. 터미널 탭은 아직 열리지 않는다. */
    data object Terminal : OpenRequest

    /** kind=chat 페이지. 채팅 탭은 아직 열리지 않는다. */
    data object Chat : OpenRequest
}

/** 파일 확장자 → 탭 종류. 여기 없는 확장자(없음 포함)는 문서 탭의 코드 보기로 연다. */
val FILE_TAB_KINDS: Map<String, TabKind> = mapOf(
    "md" to TabKind.DOCUMENT,
    "json" to TabKind.DATA,
    "yaml" to TabKind.DATA,
    "yml" to TabKind.DATA,
    "csv" to TabKind.DATA,
    "html" to TabKind.BROWSER
)

/** 요청이 여는 탭 종류. */
fun tabKindOf(request: OpenRequest): TabKind = when (request) {
    is OpenRequest.File -> FILE_TAB_KINDS[extensionOf(request.path)] ?: TabKind.DOCUMENT
    is OpenRequest.Url -> TabKind.BROWSER
    OpenRequest.Diff -> TabKind.DIFF
    OpenRequest.Terminal -> TabKind.TERMINAL
    OpenRequest.Chat -> TabKind.CHAT
}

/** 문서 탭에서 렌더하지 않고 코드 보기(편집 없음)로 보일 파일인가. 표에 없는 확장자다. */
fun isCodeView(path: String): Boolean = extensionOf(path) !in FILE_TAB_KINDS

/**
 * 파일 이름의 마지막 점 뒤를 소문자로. 점이 없거나 점으로만 시작하는 이름(`.gitignore`)은 빈
 * 문자열이다.
 */
fun extensionOf(path: String): String {
    val name = path.substringAfterLast('/').substringAfterLast('\\')
    val dot = name.lastIndexOf('.')
    return if (dot <= 0) "" else name.substring(dot + 1).lowercase()
}

/**
 * 흐름의 블록을 열 때의 요청. 머리부가 선언한 것만 쓴다: site는 `url`, term은 PTY, code는 `path`
 * (작업 폴더 기준), 나머지는 블록 파일. 메시지·run 블록은 페이지의 일부라 열지 않는다.
 */
fun openRequestFor(block: BlockHeader): OpenRequest? = when (block.type) {
    BlockType.MESSAGE, BlockType.RUN -> null
    BlockType.SITE -> block.url?.let(OpenRequest::Url)
    BlockType.TERM -> OpenRequest.Terminal
    BlockType.CODE -> block.path?.let(OpenRequest::File)
    BlockType.DOC, BlockType.DATA, BlockType.VIEW -> block.file?.let(OpenRequest::File)
}

/** 로컬 파일의 `file://` URL. 경로의 공백 등은 퍼센트 인코딩한다. */
fun fileUrl(absolutePath: String): String {
    val path = absolutePath.replace('\\', '/').let { if (it.startsWith('/')) it else "/$it" }
    return "file://" + path.split('/').joinToString("/") { encodeUrlSegment(it) }
}

private fun encodeUrlSegment(segment: String): String = buildString {
    for (byte in segment.encodeToByteArray()) {
        val c = byte.toInt() and 0xff
        val char = c.toChar()
        if ((char.isLetterOrDigit() && c < 0x80) || char in "-._~:") {
            append(char)
        } else {
            append('%').append(HEX[c shr 4]).append(HEX[c and 0xf])
        }
    }
}

private const val HEX = "0123456789ABCDEF"
