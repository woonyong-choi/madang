package madang.shared.main

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageDetail
import madang.api.model.RunRecord

/** 3열 본문의 한 항목. 블록, run 기록, 또는 보내는 중인 메시지. */
sealed interface FlowItem {
    val key: String

    data class Block(val header: BlockHeader) : FlowItem {
        override val key: String get() = header.id
    }

    data class Run(val record: RunRecord) : FlowItem {
        override val key: String get() = "run-${record.n}"
    }

    /** 보냈지만 core 페이지에 아직 없는 사용자 메시지. */
    data class Pending(val message: PendingMessage) : FlowItem {
        override val key: String get() = message.localId
    }
}

/** 블록 흐름. 각 run은 그 run을 일으킨 메시지 바로 뒤에, 짝이 없으면 끝에 둔다. */
fun pageFlow(page: PageDetail): List<FlowItem> {
    val blockIds = page.blocks.mapTo(mutableSetOf()) { it.id }
    val runsAfter = page.runs.filter { it.trigger?.message in blockIds }
        .groupBy { it.trigger?.message }
    val items = mutableListOf<FlowItem>()
    for (block in page.blocks) {
        items += FlowItem.Block(block)
        runsAfter[block.id].orEmpty().forEach { items += FlowItem.Run(it) }
    }
    page.runs.filter { it.trigger?.message !in blockIds }.forEach { items += FlowItem.Run(it) }
    return items
}

/**
 * 접힌 항목의 key.
 *
 * router 메시지와 run은 늘 접히고, user·agent 메시지는 마지막 user 메시지보다 앞이면
 * (지난 대화면) 접힌다. doc·data·view는 접히지 않는다. [expandAll]이면 아무것도 접지 않고,
 * [toggled]에 있는 항목은 규칙과 반대로 둔다.
 */
fun foldedKeys(items: List<FlowItem>, expandAll: Boolean, toggled: Set<String>): Set<String> {
    if (expandAll) return emptySet()
    val lastUser = items.indexOfLast {
        it is FlowItem.Pending ||
            (it is FlowItem.Block && it.header.isMessage(MessageRole.USER))
    }
    return items.withIndex()
        .filter { (index, item) -> foldsByRule(item, index < lastUser) != (item.key in toggled) }
        .mapTo(mutableSetOf()) { it.value.key }
}

/** 접힐 수 있는 항목인가. 접을 수 없는 항목은 클릭으로도 접지 않는다. */
fun isFoldable(item: FlowItem): Boolean = when (item) {
    is FlowItem.Run -> true
    is FlowItem.Block -> item.header.type == BlockType.MESSAGE
    is FlowItem.Pending -> false
}

private fun foldsByRule(item: FlowItem, old: Boolean): Boolean = when (item) {
    is FlowItem.Run -> true

    is FlowItem.Pending -> false

    is FlowItem.Block -> when {
        item.header.type != BlockType.MESSAGE -> false
        item.header.role == MessageRole.ROUTER -> true
        else -> old
    }
}

private fun BlockHeader.isMessage(role: MessageRole) =
    type == BlockType.MESSAGE && this.role == role

/** data 블록 표 미리보기. [rowCount]는 전체 행 수, [rows]는 앞쪽 일부. */
data class DataPreview(val columns: List<String>, val rows: List<List<String>>, val rowCount: Int)

/**
 * data 블록 내용을 표로 만든다.
 *
 * JSON 최상위 배열은 항목이 행(객체면 키가 열), 최상위 객체는 키·값 두 열이다. CSV는 첫 줄이
 * 열 이름이다. 해석할 수 없으면 null.
 */
fun dataPreview(
    content: String,
    csv: Boolean = false,
    maxRows: Int = PREVIEW_ROWS,
    maxColumns: Int = PREVIEW_COLUMNS
): DataPreview? {
    if (csv) return csvPreview(content, maxRows, maxColumns)
    val root = runCatching { Json.parseToJsonElement(content) }.getOrNull() ?: return null
    return when (root) {
        is JsonArray -> arrayPreview(root, maxRows, maxColumns)

        is JsonObject -> DataPreview(
            columns = listOf(KEY_COLUMN, VALUE_COLUMN),
            rows = root.entries.take(maxRows).map { (key, value) -> listOf(key, cellText(value)) },
            rowCount = root.size
        )

        else -> null
    }
}

private fun arrayPreview(array: JsonArray, maxRows: Int, maxColumns: Int): DataPreview {
    val objects = array.filterIsInstance<JsonObject>()
    if (objects.size != array.size || objects.isEmpty()) {
        return DataPreview(
            columns = listOf(VALUE_COLUMN),
            rows = array.take(maxRows).map { listOf(cellText(it)) },
            rowCount = array.size
        )
    }
    val columns = objects.flatMap { it.keys }.distinct().take(maxColumns)
    val rows = objects.take(maxRows).map { row -> columns.map { cellText(row[it]) } }
    return DataPreview(columns, rows, array.size)
}

private fun csvPreview(content: String, maxRows: Int, maxColumns: Int): DataPreview? {
    val lines = content.lines().filter { it.isNotBlank() }
    val header = lines.firstOrNull() ?: return null
    val columns = header.split(',').map { it.trim() }.take(maxColumns)
    val body = lines.drop(1)
    val rows = body.take(maxRows).map { line ->
        line.split(',').map { it.trim() }.take(columns.size)
    }
    return DataPreview(columns, rows, body.size)
}

private fun cellText(value: JsonElement?): String = when (value) {
    null, JsonNull -> ""
    is JsonPrimitive -> value.content
    is JsonArray -> "[${value.size}]"
    is JsonObject -> "{${value.size}}"
}

private const val PREVIEW_ROWS = 5
private const val PREVIEW_COLUMNS = 6
private const val KEY_COLUMN = "key"
private const val VALUE_COLUMN = "value"
