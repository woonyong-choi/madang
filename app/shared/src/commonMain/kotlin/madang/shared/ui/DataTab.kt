package madang.shared.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import madang.shared.main.DataDraft
import madang.shared.main.DataFormat
import madang.shared.main.DataNode
import madang.shared.main.TreeRow
import madang.shared.main.dataPreview
import madang.shared.main.initiallyExpanded
import madang.shared.main.parseData
import madang.shared.main.treeRows

/**
 * 데이터 탭이 원문을 고칠 수 있을 때의 대상. 블록 파일만 고친다(저장은 core).
 *
 * @property draft 고치는 중인 원문. 없으면 저장된 내용 그대로다.
 */
data class DataEdit(val block: String, val draft: DataDraft?)

/** 데이터 탭의 보기. */
private enum class DataMode { TABLE, TREE, SOURCE }

/**
 * 데이터 탭. JSON·YAML·CSV를 표·트리·원문으로 본다. 형식은 파일 확장자가 정한다.
 *
 * [edit]가 있으면 원문 보기에서 고쳐 저장한다. 표·트리는 고치는 중인 원문을 따라 바뀐다. 없으면
 * (작업 폴더 파일) 읽기만 한다.
 *
 * @param key 보기 상태(보기 종류, 펼친 마디)를 기억하는 key. 블록 id나 파일 경로.
 * @param facts 서랍 아래쪽에 붙일 파일 정보.
 */
@Composable
fun DataTab(
    key: String,
    content: String?,
    format: DataFormat,
    edit: DataEdit?,
    actions: TabActions,
    modifier: Modifier,
    facts: @Composable ColumnScope.() -> Unit
) {
    val strings = LocalStrings.current.tabs
    val text = edit?.draft?.text ?: content
    val root = remember(text, format) { text?.let { parseData(it, format) } }
    val table = remember(text, format) {
        text?.let { dataPreview(it, format, maxRows = Int.MAX_VALUE, maxColumns = Int.MAX_VALUE) }
    }
    var mode by remember(key) { mutableStateOf<DataMode?>(null) }
    val shown = mode ?: when {
        table != null -> DataMode.TABLE
        root != null -> DataMode.TREE
        else -> DataMode.SOURCE
    }
    var expanded by remember(key) { mutableStateOf<Set<String>?>(null) }
    TabFrame(
        modifier,
        actions,
        main = {
            when {
                text == null -> Placeholder(strings.loading)

                shown == DataMode.SOURCE -> DataSource(text, edit, actions)

                root == null -> {
                    Notice(strings.notParsed(format.name))
                    SourceText(text)
                }

                shown == DataMode.TABLE && table != null -> DataTable(table.columns, table.rows)

                else -> {
                    if (shown == DataMode.TABLE) Notice(strings.notTable)
                    val open = expanded ?: initiallyExpanded(root)
                    DataTree(root, open) { path ->
                        expanded = if (path in open) open - path else open + path
                    }
                }
            }
        },
        drawer = {
            ModeChips(
                listOf(
                    DataMode.TABLE to strings.table,
                    DataMode.TREE to strings.tree,
                    DataMode.SOURCE to strings.source
                ),
                shown
            ) { mode = it }
            DrawerFact(strings.format, format.name.lowercase())
            table?.let { DrawerFact(LocalStrings.current.navigator.rows(it.rowCount), null) }
            facts()
            if (edit != null) DrawerFact(strings.editHint, null)
        }
    )
}

/** 원문 보기. 고칠 수 있으면 줄 번호 편집기와 저장·되돌리기, 아니면 읽기 전용 원문이다. */
@Composable
private fun DataSource(text: String, edit: DataEdit?, actions: TabActions) {
    val strings = LocalStrings.current.tabs
    if (edit == null) {
        Notice(strings.readOnly)
        SourceText(text)
        return
    }
    val draft = edit.draft
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.padding(bottom = 8.dp)
    ) {
        Button(
            onClick = { actions.data.save(edit.block) },
            enabled = draft != null && !draft.saving
        ) { Text(if (draft?.saving == true) strings.saving else strings.save) }
        TextButton(
            onClick = { actions.data.discard(edit.block) },
            enabled = draft != null && !draft.saving,
            modifier = Modifier.padding(start = 8.dp)
        ) { Text(strings.discard) }
    }
    draft?.issues?.filter { it.line == null }?.forEach { IssueText(it.message) }
    draft?.error?.let { IssueText(it) }
    LineEditor(
        text,
        draft?.issuesByLine.orEmpty(),
        onEdit = { actions.data.edit(edit.block, it) },
        onEditing = actions.onEditing
    )
}

@Composable
private fun DataTable(columns: List<String>, rows: List<List<String>>) {
    Column(modifier = Modifier.horizontalScroll(rememberScrollState())) {
        TableRow(columns, header = true)
        rows.forEach { TableRow(it, header = false) }
    }
}

/** 트리 보기. 목록·매핑 줄을 누르면 펼치고 접는다. */
@Composable
private fun DataTree(root: DataNode, expanded: Set<String>, toggle: (String) -> Unit) {
    Column(modifier = Modifier.horizontalScroll(rememberScrollState())) {
        treeRows(root, expanded).forEach { TreeLine(it, toggle) }
    }
}

@Composable
private fun TreeLine(row: TreeRow, toggle: (String) -> Unit) {
    val colors = MaterialTheme.colorScheme
    Row(
        modifier = Modifier
            .then(if (row.expandable) Modifier.clickable { toggle(row.path) } else Modifier)
            .padding(start = TREE_INDENT * row.depth, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (row.expandable) {
            Icon(
                if (row.expanded) {
                    Icons.Outlined.KeyboardArrowDown
                } else {
                    Icons.AutoMirrored.Outlined.KeyboardArrowRight
                },
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = colors.onSurfaceVariant
            )
        } else {
            Spacer(Modifier.width(16.dp))
        }
        Text(
            row.label,
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            color = colors.primary,
            modifier = Modifier.padding(start = 4.dp, end = 8.dp)
        )
        Text(
            row.summary,
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            color = if (row.expandable) colors.onSurfaceVariant else colors.onSurface,
            softWrap = false
        )
    }
}

/** 여러 보기 중 하나를 고르는 칩. */
@Composable
private fun <T> ModeChips(options: List<Pair<T, String>>, selected: T, pick: (T) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        for ((value, label) in options) {
            FilterChip(
                selected = value == selected,
                onClick = { pick(value) },
                label = { Text(label) }
            )
        }
    }
    HorizontalDivider(modifier = Modifier.padding(vertical = 6.dp))
}

@Composable
private fun Notice(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
    )
}

@Composable
private fun IssueText(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.error,
        modifier = Modifier.padding(bottom = 4.dp)
    )
}

private val TREE_INDENT = 16.dp
