package madang.shared.main

/**
 * 머리부의 최상위 키 하나.
 *
 * [value]는 `키:` 뒤의 원문이다. 들여쓴 줄·목록 줄처럼 다음 키 전까지의 줄이 줄바꿈으로 이어
 * 붙는다. YAML로 해석하지 않으므로 주석과 흐름 형식이 그대로 남는다.
 *
 * @property line 키가 있는 파일 줄(1부터).
 * @property lineCount 이 키가 차지하는 줄 수.
 */
data class HeaderField(val key: String, val value: String, val line: Int, val lineCount: Int) {
    operator fun contains(fileLine: Int): Boolean = fileLine in line until line + lineCount
}

/**
 * md 파일을 머리부(`---`로 감싼 front matter)와 본문으로 나눈 것.
 *
 * 머리부가 없으면 [fields]가 비고 파일 전체가 [body]다.
 *
 * @property bodyLine 본문 첫 줄의 파일 줄(1부터).
 */
data class MemoryParts(
    val hasHeader: Boolean,
    val fields: List<HeaderField>,
    val body: String,
    val bodyLine: Int
)

/** 줄 머리의 `키:`. 들여쓰지 않은 줄만 최상위 키다. */
private val KEY_LINE = Regex("^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")

private const val DELIMITER = "---"

/** [text]를 머리부의 최상위 키들과 본문으로 나눈다. */
fun splitMemory(text: String): MemoryParts {
    val lines = text.split('\n')
    val end = headerEnd(lines) ?: return MemoryParts(false, emptyList(), text, 1)
    val fields = mutableListOf<HeaderField>()
    for (index in 1 until end) {
        val match = KEY_LINE.matchEntire(lines[index])
        val last = fields.lastOrNull()
        when {
            match != null -> fields += HeaderField(
                key = match.groupValues[1],
                value = match.groupValues[2].removePrefix(" "),
                line = index + 1,
                lineCount = 1
            )

            last != null -> fields[fields.lastIndex] = last.copy(
                value = if (last.lineCount == 1 && last.value.isEmpty()) {
                    lines[index]
                } else {
                    last.value + "\n" + lines[index]
                },
                lineCount = last.lineCount + 1
            )
        }
    }
    return MemoryParts(true, fields, lines.drop(end + 1).joinToString("\n"), end + 2)
}

/**
 * [text] 머리부의 [key] 값을 [value]로 바꾼다. 다른 줄은 한 글자도 건드리지 않는다.
 *
 * 값의 첫 줄이 비었거나 들여쓰기·목록(`- `)으로 시작하면 키 다음 줄부터 쓴다. 키가 없으면 [text]를
 * 그대로 돌려준다.
 */
fun withHeaderField(text: String, key: String, value: String): String {
    val field = splitMemory(text).fields.firstOrNull { it.key == key } ?: return text
    val lines = text.split('\n')
    val replaced = lines.take(field.line - 1) + fieldLines(key, value) +
        lines.drop(field.line - 1 + field.lineCount)
    return replaced.joinToString("\n")
}

private fun fieldLines(key: String, value: String): List<String> {
    val first = value.substringBefore('\n')
    val block = first.isEmpty() || first.startsWith(' ') || first.startsWith('\t') ||
        first == "-" || first.startsWith("- ")
    return when {
        value.isEmpty() -> listOf("$key:")
        block -> listOf("$key:") + value.split('\n')
        else -> ("$key: $value").split('\n')
    }
}

/** 머리부를 닫는 `---`의 줄 인덱스. 머리부가 없으면 null. */
private fun headerEnd(lines: List<String>): Int? {
    if (lines.firstOrNull() != DELIMITER) return null
    return (1 until lines.size).firstOrNull { lines[it] == DELIMITER }
}
