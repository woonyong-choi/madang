package madang.shared.main

/**
 * 통합 diff의 한 줄.
 *
 * @property oldLine 바뀌기 전 파일의 줄 번호. 더한 줄과 머리 줄은 null.
 * @property newLine 바뀐 뒤 파일의 줄 번호. 뺀 줄과 머리 줄은 null.
 */
data class DiffLine(val kind: Kind, val text: String, val oldLine: Int?, val newLine: Int?) {
    /** 줄 종류. [HUNK]는 `@@` 머리, [NOTE]는 `\ No newline at end of file` 같은 알림. */
    enum class Kind { HUNK, CONTEXT, ADDED, REMOVED, NOTE }
}

/**
 * diff 안의 파일 하나.
 *
 * @property path 바뀐 뒤 경로. 지운 파일이면 지우기 전 경로.
 * @property oldPath 이름을 바꿨을 때만 이전 경로.
 * @property binary git이 내용 대신 "Binary files … differ"만 알려 줬다.
 */
data class DiffFile(
    val path: String,
    val change: Change,
    val lines: List<DiffLine>,
    val oldPath: String? = null,
    val binary: Boolean = false
) {
    enum class Change { MODIFIED, ADDED, DELETED, RENAMED }

    val added: Int get() = lines.count { it.kind == DiffLine.Kind.ADDED }

    val removed: Int get() = lines.count { it.kind == DiffLine.Kind.REMOVED }
}

/** core가 준 통합 diff 텍스트를 파일별로 나눈다. 첫 `diff --git` 앞의 줄은 버린다. */
fun parseDiff(text: String): List<DiffFile> {
    val files = mutableListOf<DiffFile>()
    var current: FileBuilder? = null
    for (line in text.lines()) {
        if (line.startsWith(FILE_HEADER)) {
            current?.let { files += it.build() }
            current = FileBuilder(line.removePrefix(FILE_HEADER))
            continue
        }
        current?.read(line)
    }
    current?.let { files += it.build() }
    return files
}

/** 파일 하나의 줄을 차례로 읽어 [DiffFile]을 만든다. */
private class FileBuilder(header: String) {
    private val headerPath = header.substringAfterLast(" b/", header)
    private var oldPath: String? = null
    private var newPath: String? = null
    private var renamedFrom: String? = null
    private var change = DiffFile.Change.MODIFIED
    private var binary = false
    private val lines = mutableListOf<DiffLine>()
    private var inHunk = false
    private var oldNext = 0
    private var newNext = 0

    fun read(line: String) {
        if (line.startsWith("@@")) return startHunk(line)
        if (inHunk) return readHunkLine(line)
        when {
            line.startsWith("new file mode") -> change = DiffFile.Change.ADDED
            line.startsWith("deleted file mode") -> change = DiffFile.Change.DELETED
            line.startsWith("rename from ") -> renamedFrom = line.removePrefix("rename from ")
            line.startsWith("rename to ") -> change = DiffFile.Change.RENAMED
            line.startsWith("Binary files ") -> binary = true
            line.startsWith("--- ") -> oldPath = sidePath(line.removePrefix("--- "), "a/")
            line.startsWith("+++ ") -> newPath = sidePath(line.removePrefix("+++ "), "b/")
        }
    }

    fun build(): DiffFile = DiffFile(
        path = newPath ?: oldPath ?: headerPath,
        change = change,
        lines = lines.toList(),
        oldPath = renamedFrom.takeIf { change == DiffFile.Change.RENAMED },
        binary = binary
    )

    private fun startHunk(line: String) {
        val match = HUNK.find(line)
        oldNext = match?.groupValues?.get(1)?.toIntOrNull() ?: 0
        newNext = match?.groupValues?.get(2)?.toIntOrNull() ?: 0
        inHunk = true
        lines += DiffLine(DiffLine.Kind.HUNK, line, null, null)
    }

    private fun readHunkLine(line: String) {
        val body = line.drop(1)
        lines += when (line.firstOrNull()) {
            '+' -> DiffLine(DiffLine.Kind.ADDED, body, null, newNext++)

            '-' -> DiffLine(DiffLine.Kind.REMOVED, body, oldNext++, null)

            '\\' -> DiffLine(DiffLine.Kind.NOTE, line, null, null)

            ' ' -> DiffLine(DiffLine.Kind.CONTEXT, body, oldNext++, newNext++)

            // 텍스트 끝의 빈 줄. 문맥 줄은 늘 공백으로 시작하므로 diff의 줄이 아니다.
            else -> return
        }
    }

    /** `--- a/x`·`+++ b/x`의 경로. `/dev/null`이면 null. */
    private fun sidePath(value: String, prefix: String): String? = when {
        value == DEV_NULL -> null
        else -> value.removePrefix(prefix).substringBefore('\t')
    }
}

private const val FILE_HEADER = "diff --git a/"
private const val DEV_NULL = "/dev/null"
private val HUNK = Regex("""^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@""")
