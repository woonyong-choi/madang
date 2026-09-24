package madang.shared.main

import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.RunRecord

/** 페이지 기록 폴더. page.md·ledger.md가 프로젝트 폴더의 `.madang/pages/<id>/`에 있다. */
fun pageFolder(projectPath: String, pageId: String): String =
    "${projectPath.trimEnd('/')}/$PAGES_DIR/$pageId"

/** 페이지 기록 폴더 [folder]의 본문 파일(page.md) 경로. */
fun pageFile(folder: String): String = "$folder/$PAGE_FILE"

/**
 * 페이지 흐름을 렌더러에 넘길 page.md 모양의 원문으로 모은다. 그리는 일은 렌더러가 한다.
 *
 * [source](page.md 원문)가 있으면 개요와 메시지 블록은 원문 그대로 쓴다. 블록 머리 주석의
 * `ask`·`answer`·`options` 같은 필드가 살아 렌더러가 묻는 블록·답으로 그린다. 원문이 없으면
 * core가 준 머리부로 같은 모양을 만든다. doc·data 같은 파일 블록은 page.md 본문에 없으므로 흐름
 * 순서 자리에 머리 주석과 내용을 끼운다. 보내는 중인 메시지는 끝에 흐린 요청 블록으로 붙인다.
 *
 * @param only 주면 이 블록만 담고 개요와 보내는 중인 메시지는 뺀다(run 탭).
 */
fun pageMarkdown(
    open: OpenPage,
    source: String?,
    only: ((BlockHeader) -> Boolean)? = null
): String {
    val sections = source?.let(::messageSections)
    val out = StringBuilder()
    if (only == null) out.append(sections?.overview ?: open.detail.overview.orEmpty())
    for (item in open.flowItems) {
        val section = when (item) {
            is FlowItem.Block -> item.header.takeIf { only == null || only(it) }?.let {
                sections?.blocks?.get(it.id) ?: blockSection(it, open.contents[it.id])
            }

            is FlowItem.Pending -> if (only == null) pendingSection(item.message.text) else null

            is FlowItem.Run -> null
        }
        section?.let { out.appendSection(it) }
    }
    return out.toString()
}

/**
 * 페이지의 실행 기록. 렌더러가 그 실행을 일으킨 메시지(`after`) 뒤에 접힌 실행 블록으로 그린다.
 *
 * @param summary 실행 한 줄 요약(토큰·시간·바뀐 파일).
 */
fun pageRuns(runs: List<RunRecord>, summary: (RunRecord) -> String): List<RunEntry> = runs.map {
    RunEntry(
        n = it.n,
        after = it.trigger?.message,
        title = listOfNotNull(it.runner, it.model).joinToString("/").ifEmpty { null },
        summary = summary(it),
        status = it.resultStatus?.value,
        files = it.changedFiles
    )
}

/** page.md 원문의 개요(첫 블록 머리 앞, 머리부 포함)와 블록 id별 원문(머리 주석부터). */
private class Sections(val overview: String, val blocks: Map<String, String>)

private fun messageSections(source: String): Sections {
    val heads = BLOCK_HEAD.findAll(source).toList()
    val blocks = heads.withIndex().associate { (i, head) ->
        val end = heads.getOrNull(i + 1)?.range?.first ?: source.length
        head.groupValues[1] to source.substring(head.range.first, end).trimEnd()
    }
    return Sections(source.substring(0, heads.firstOrNull()?.range?.first ?: source.length), blocks)
}

/** core 머리부로 만든 블록 원문. 메시지는 page.md와 같은 모양이고, 파일 블록은 내용을 담는다. */
private fun blockSection(block: BlockHeader, content: String?): String {
    if (block.type == BlockType.MESSAGE) {
        val attrs = listOfNotNull(
            block.run?.let { "run" to it.toString() },
            block.target?.let { "target" to (it.block ?: PAGE_TARGET) }
        )
        return head(block.id, block.ts.orEmpty(), block.role?.value.orEmpty(), attrs) +
            "\n" + block.text.orEmpty()
    }
    val openable = openTargetFor(FlowItem.Block(block)) != null
    val attrs = listOfNotNull(
        (block.file ?: block.path ?: block.url)?.takeIf { openable }?.let { "file" to it },
        block.title?.let { "title" to it }
    )
    return head(block.id, "", block.type.value, attrs) + "\n" + fileBody(block, content)
}

/** 파일 블록 본문. 데이터는 코드 펜스로, 나머지 md는 그대로. 내용이 없으면 비운다. */
private fun fileBody(block: BlockHeader, content: String?): String {
    val text = content ?: return ""
    val format = block.file?.let(::dataFormatOf) ?: return text
    return "```${format.name.lowercase()}\n${text.trimEnd()}\n```"
}

private fun pendingSection(text: String): String =
    head(PENDING_ID, "", USER_ROLE, listOf("pending" to "true")) + "\n" + text

private fun head(
    id: String,
    time: String,
    role: String,
    attrs: List<Pair<String, String>>
): String {
    val fields = attrs.joinToString(" ") { (key, value) -> "$key=${encodeAttr(value)}" }
    val head = "<!-- $id | $time | $role"
    return if (fields.isEmpty()) "$head -->" else "$head | $fields -->"
}

/** 머리 주석 값. 공백·`|`·`%` 등은 퍼센트 인코딩한다(렌더러가 푼다). */
private fun encodeAttr(value: String): String = buildString {
    for (byte in value.encodeToByteArray()) {
        val c = byte.toInt() and BYTE_MASK
        val char = c.toChar()
        if ((char.isLetterOrDigit() && c < ASCII_LIMIT) || char in SAFE_ATTR_CHARS) {
            append(char)
        } else {
            append('%').append(HEX_DIGITS[c shr NIBBLE]).append(HEX_DIGITS[c and NIBBLE_MASK])
        }
    }
}

private fun StringBuilder.appendSection(section: String) {
    if (isNotEmpty()) {
        while (!endsWith("\n\n")) append('\n')
    }
    append(section.trimEnd()).append('\n')
}

private const val PAGES_DIR = ".madang/pages"
private const val PAGE_FILE = "page.md"
private const val PAGE_TARGET = "page"
private const val PENDING_ID = "b0"
private const val USER_ROLE = "user"
private const val SAFE_ATTR_CHARS = "-._~/:,@+"
private const val HEX_DIGITS = "0123456789ABCDEF"
private const val BYTE_MASK = 0xff
private const val ASCII_LIMIT = 0x80
private const val NIBBLE = 4
private const val NIBBLE_MASK = 0xf

// core `store/pages.py`의 블록 머리 규칙과 같다.
private val BLOCK_HEAD = Regex("^<!--\\s*(b\\d+)\\s*\\|", RegexOption.MULTILINE)
