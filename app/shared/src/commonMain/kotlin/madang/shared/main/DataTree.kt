package madang.shared.main

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** 데이터 탭이 읽는 형식. 파일 확장자로만 정한다. */
enum class DataFormat { JSON, YAML, CSV }

/** 확장자가 가리키는 데이터 형식. 데이터 파일이 아니면 null. */
fun dataFormatOf(path: String): DataFormat? = when (extensionOf(path)) {
    "json" -> DataFormat.JSON
    "yaml", "yml" -> DataFormat.YAML
    "csv" -> DataFormat.CSV
    else -> null
}

/** 해석한 데이터의 한 마디. 형식에 상관없이 같은 모양이다. */
sealed interface DataNode {
    /** 값 하나. null은 JSON `null`·YAML `~`. */
    data class Scalar(val text: String?) : DataNode

    data class Sequence(val items: List<DataNode>) : DataNode

    /** 키 순서를 파일 그대로 둔다. */
    data class Mapping(val entries: List<Pair<String, DataNode>>) : DataNode
}

/** [content]를 [format]으로 해석한다. 해석할 수 없으면 null. CSV는 행마다 열 이름 → 칸이다. */
fun parseData(content: String, format: DataFormat): DataNode? = when (format) {
    DataFormat.JSON -> runCatching { Json.parseToJsonElement(content) }.getOrNull()?.toNode()

    DataFormat.YAML -> runCatching { loadYaml(content) }.getOrNull()?.let(::yamlNode)

    DataFormat.CSV -> csvRows(content)?.let { (columns, rows) ->
        DataNode.Sequence(rows.map { row -> DataNode.Mapping(columns.zip(row.map(::scalar))) })
    }
}

/**
 * YAML 문서 하나를 읽어 `Map`·`List`·스칼라로 돌려준다. 태그로 임의 객체를 만들지 않는다. 문법이
 * 틀리면 예외를 던진다.
 */
expect fun loadYaml(content: String): Any?

/** data 블록 표 미리보기. [rowCount]는 전체 행 수, [rows]는 앞쪽 일부. */
data class DataPreview(val columns: List<String>, val rows: List<List<String>>, val rowCount: Int)

/**
 * 데이터 파일 내용을 표로 만든다.
 *
 * 최상위 목록은 항목이 행(매핑이면 키가 열), 최상위 매핑은 키·값 두 열이다. CSV는 첫 줄이 열
 * 이름이다. 해석할 수 없거나 최상위가 값 하나면 null.
 */
fun dataPreview(
    content: String,
    format: DataFormat = DataFormat.JSON,
    maxRows: Int = PREVIEW_ROWS,
    maxColumns: Int = PREVIEW_COLUMNS
): DataPreview? {
    if (format == DataFormat.CSV) return csvPreview(content, maxRows, maxColumns)
    return when (val root = parseData(content, format)) {
        is DataNode.Sequence -> sequencePreview(root, maxRows, maxColumns)

        is DataNode.Mapping -> DataPreview(
            columns = listOf(KEY_COLUMN, VALUE_COLUMN),
            rows = root.entries.take(maxRows).map { (key, value) -> listOf(key, cellText(value)) },
            rowCount = root.entries.size
        )

        is DataNode.Scalar, null -> null
    }
}

/**
 * 트리 보기의 한 줄.
 *
 * @property path 루트에서 이 마디까지의 key(`$`, `$/work`, `$/work/0`). 펼침 상태의 key다.
 * @property label 부모 매핑의 키 또는 목록의 번호. 루트는 빈 문자열.
 * @property summary 값이면 그 값, 목록·매핑이면 `[n]`·`{n}`.
 * @property expandable 목록·매핑이다.
 */
data class TreeRow(
    val path: String,
    val depth: Int,
    val label: String,
    val summary: String,
    val expandable: Boolean,
    val expanded: Boolean
)

/** 트리를 [expanded]에 든 마디만 펼쳐 줄로 편다. 루트 줄은 빼고 루트의 자식부터 보인다. */
fun treeRows(root: DataNode, expanded: Set<String>): List<TreeRow> {
    val rows = mutableListOf<TreeRow>()
    fun visit(node: DataNode, path: String, depth: Int) {
        for ((label, child) in children(node)) {
            val childPath = "$path/$label"
            val open = childPath in expanded
            rows +=
                TreeRow(childPath, depth, label, cellText(child), child !is DataNode.Scalar, open)
            if (open) visit(child, childPath, depth + 1)
        }
    }
    visit(root, ROOT_PATH, 0)
    return rows
}

/** 처음 열 때 펼쳐 둘 마디: 루트 아래 [depth]단계까지. */
fun initiallyExpanded(root: DataNode, depth: Int = INITIAL_DEPTH): Set<String> {
    val open = mutableSetOf<String>()
    fun visit(node: DataNode, path: String, level: Int) {
        if (level >= depth) return
        for ((label, child) in children(node)) {
            if (child is DataNode.Scalar) continue
            val childPath = "$path/$label"
            open += childPath
            visit(child, childPath, level + 1)
        }
    }
    visit(root, ROOT_PATH, 0)
    return open
}

private fun children(node: DataNode): List<Pair<String, DataNode>> = when (node) {
    is DataNode.Scalar -> emptyList()
    is DataNode.Sequence -> node.items.mapIndexed { index, item -> index.toString() to item }
    is DataNode.Mapping -> node.entries
}

private fun JsonElement.toNode(): DataNode = when (this) {
    JsonNull -> DataNode.Scalar(null)
    is JsonPrimitive -> DataNode.Scalar(content)
    is JsonArray -> DataNode.Sequence(map { it.toNode() })
    is JsonObject -> DataNode.Mapping(entries.map { (key, value) -> key to value.toNode() })
}

private fun yamlNode(value: Any?): DataNode = when (value) {
    null -> DataNode.Scalar(null)
    is Map<*, *> -> DataNode.Mapping(value.entries.map { (k, v) -> k.toString() to yamlNode(v) })
    is List<*> -> DataNode.Sequence(value.map(::yamlNode))
    else -> DataNode.Scalar(value.toString())
}

private fun scalar(text: String): DataNode = DataNode.Scalar(text)

private fun sequencePreview(
    sequence: DataNode.Sequence,
    maxRows: Int,
    maxColumns: Int
): DataPreview {
    val items = sequence.items
    val mappings = items.filterIsInstance<DataNode.Mapping>()
    if (mappings.size != items.size || mappings.isEmpty()) {
        return DataPreview(
            columns = listOf(VALUE_COLUMN),
            rows = items.take(maxRows).map { listOf(cellText(it)) },
            rowCount = items.size
        )
    }
    val columns = mappings.flatMap { row -> row.entries.map { it.first } }.distinct()
        .take(maxColumns)
    val rows = mappings.take(maxRows).map { row ->
        val cells = row.entries.toMap()
        columns.map { cellText(cells[it]) }
    }
    return DataPreview(columns, rows, items.size)
}

private fun csvPreview(content: String, maxRows: Int, maxColumns: Int): DataPreview? {
    val (header, body) = csvRows(content) ?: return null
    val columns = header.take(maxColumns)
    val rows = body.take(maxRows).map { it.take(columns.size) }
    return DataPreview(columns, rows, body.size)
}

/** CSV를 열 이름과 행으로 나눈다. 칸은 쉼표로만 나눈다(따옴표 해석 없음). 빈 줄은 건너뛴다. */
private fun csvRows(content: String): Pair<List<String>, List<List<String>>>? {
    val lines = content.lines().filter { it.isNotBlank() }
    val header = lines.firstOrNull() ?: return null
    return header.split(',').map { it.trim() } to
        lines.drop(1).map { line -> line.split(',').map { it.trim() } }
}

private fun cellText(value: DataNode?): String = when (value) {
    null -> ""
    is DataNode.Scalar -> value.text.orEmpty()
    is DataNode.Sequence -> "[${value.items.size}]"
    is DataNode.Mapping -> "{${value.entries.size}}"
}

private const val PREVIEW_ROWS = 5
private const val PREVIEW_COLUMNS = 6
private const val KEY_COLUMN = "key"
private const val VALUE_COLUMN = "value"
private const val ROOT_PATH = "$"
private const val INITIAL_DEPTH = 2
