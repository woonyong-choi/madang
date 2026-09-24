package madang.shared.onboarding

private const val RUNNERS_KEY = "runners"
private const val BIN_KEY = "bin"
private const val INDENT_STEP = "  "

/**
 * config.yaml 원문에서 `runners.<runner>.bin`을 [bin]으로 바꾼 원문을 돌려준다.
 *
 * 주석·순서·다른 값은 그대로 둔다. 들여쓰기 블록 형식만 다루고, 절이나 키가 없으면 만든다.
 * `runners`나 러너 항목이 한 줄 형식(`runners: {…}`)이면 고칠 수 없으므로
 * [IllegalArgumentException]을 던진다.
 */
fun withRunnerBin(config: String, runner: String, bin: String): String {
    val lines = config.lines().toMutableList()
    if (lines.lastOrNull()?.isEmpty() == true) lines.removeAt(lines.lastIndex)
    val binLine = "$BIN_KEY: ${yamlQuoted(bin)}"

    val runners = lines.keyLine(RUNNERS_KEY, indent = "", from = 0, until = lines.size)
    if (runners == null) {
        lines += listOf("$RUNNERS_KEY:", "$INDENT_STEP$runner:", "$INDENT_STEP$INDENT_STEP$binLine")
        return lines.joinToString("\n", postfix = "\n")
    }
    lines.requireBlock(runners)
    val runnersEnd = lines.blockEnd(runners, parentIndent = "")
    val entryIndent = lines.childIndent(runners, runnersEnd) ?: INDENT_STEP

    val entry = lines.keyLine(runner, entryIndent, runners + 1, runnersEnd)
    if (entry == null) {
        lines.addAll(runnersEnd, listOf("$entryIndent$runner:", "$entryIndent$INDENT_STEP$binLine"))
        return lines.joinToString("\n", postfix = "\n")
    }
    lines.requireBlock(entry)
    val entryEnd = lines.blockEnd(entry, entryIndent)
    val fieldIndent = lines.childIndent(entry, entryEnd) ?: "$entryIndent$INDENT_STEP"

    val field = lines.keyLine(BIN_KEY, fieldIndent, entry + 1, entryEnd)
    if (field == null) {
        lines.add(entry + 1, "$fieldIndent$binLine")
    } else {
        lines[field] = "$fieldIndent$binLine"
    }
    return lines.joinToString("\n", postfix = "\n")
}

/** YAML 큰따옴표 문자열. 경로의 공백·`#`·`:`를 값으로 읽게 한다. */
private fun yamlQuoted(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

/** 빈 줄과 주석만 있는 줄은 구조에 들어가지 않는다. */
private fun String.isContent(): Boolean = isNotBlank() && !trimStart().startsWith("#")

private fun String.indent(): String = takeWhile { it == ' ' }

/** [from]부터 [until] 앞까지에서 들여쓰기가 정확히 [indent]인 `key:` 줄의 번호. */
private fun List<String>.keyLine(key: String, indent: String, from: Int, until: Int): Int? =
    (from until until).firstOrNull { i ->
        val line = this[i]
        line.isContent() && line.indent() == indent &&
            line.substring(indent.length).let { it == "$key:" || it.startsWith("$key: ") }
    }

/** `key:` 뒤에 주석 말고 값이 있으면 한 줄 형식이다. */
private fun List<String>.requireBlock(index: Int) {
    val rest = this[index].substringAfter(':').trim()
    require(rest.isEmpty() || rest.startsWith("#")) {
        "unsupported-config-layout: ${this[index].trim()}"
    }
}

/** [start] 줄 블록의 마지막 내용 줄 다음 번호. 뒤따르는 빈 줄·주석은 다음 절의 것으로 본다. */
private fun List<String>.blockEnd(start: Int, parentIndent: String): Int {
    var end = start + 1
    for (i in start + 1 until size) {
        val line = this[i]
        if (!line.isContent()) continue
        if (line.indent().length <= parentIndent.length) break
        end = i + 1
    }
    return end
}

/** 블록 첫 내용 줄의 들여쓰기. 블록이 비었으면 null. */
private fun List<String>.childIndent(start: Int, end: Int): String? =
    (start + 1 until end).firstOrNull { this[it].isContent() }?.let { this[it].indent() }
