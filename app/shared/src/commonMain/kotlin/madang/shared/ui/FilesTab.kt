package madang.shared.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.InsertDriveFile
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.FileLens
import madang.shared.main.FileRow
import madang.shared.main.FilesState
import madang.shared.main.Load

/** 파일 탭 조작. [open]은 작업 폴더 파일의 절대 경로를 가운데 열 탭 규칙으로 연다. */
class FilesActions(
    val setLens: (FileLens) -> Unit,
    val toggle: (String) -> Unit,
    val reload: () -> Unit,
    val startRun: (String) -> Unit,
    val open: (String) -> Unit
)

/**
 * 사이드바 파일 탭: 워크트리(또는 프로젝트 폴더) 트리. `.madang/`은 맨 위에 접힌 채로 있다.
 *
 * 렌즈는 전체 / 이 페이지 / 변경됨이다. 실행 배지는 `runs:`에 선언된 폴더에만 붙고 누르면 core가
 * 그 실행 대상을 띄운다. 파일을 두 번 누르면 탭 종류 규칙대로 열고, 배지가 있는 폴더를 두 번
 * 누르면 실행한다.
 */
@Composable
fun FilesTab(state: FilesState, actions: FilesActions, modifier: Modifier) {
    val strings = LocalStrings.current.side
    Column(modifier = modifier.padding(horizontal = 8.dp)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.padding(top = 6.dp)
        ) {
            state.lenses.forEach { lens ->
                FilterChip(
                    selected = lens == state.lens,
                    onClick = { actions.setLens(lens) },
                    label = {
                        Text(strings.lens(lens), style = MaterialTheme.typography.labelSmall)
                    }
                )
            }
            Spacer(Modifier.weight(1f))
            ToolbarIcon(Icons.Outlined.Refresh, strings.reload, actions.reload)
        }
        val tree = (state.tree as? Load.Ready)?.value
        if (tree != null && tree.runs.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    tree.root.substringAfterLast('/'),
                    style = MaterialTheme.typography.labelMedium,
                    fontFamily = FontFamily.Monospace
                )
                tree.runs.forEach { name -> SideBadge(strings.runBadge) { actions.startRun(name) } }
            }
        }
        state.error?.let { SideError(it) }
        when (val load = state.tree) {
            null -> SideNote(if (state.noRepository) strings.notRepository else strings.noProject)
            Load.Loading -> SideNote(strings.loading)
            is Load.Failed -> SideError(strings.failed(load.message))
            is Load.Ready -> FileList(state, actions, load.value.truncated, Modifier.weight(1f))
        }
    }
}

@Composable
private fun FileList(
    state: FilesState,
    actions: FilesActions,
    truncated: Boolean,
    modifier: Modifier
) {
    val strings = LocalStrings.current.side
    val rows = state.rows
    if (rows.isEmpty()) SideNote(strings.filesEmpty)
    if (truncated) SideNote(strings.filesTruncated)
    LazyColumn(modifier = modifier.fillMaxWidth()) {
        items(rows, key = { it.path }) { row ->
            FileLine(row, actions) { state.absolutePath(row)?.let(actions.open) }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun FileLine(row: FileRow, actions: FilesActions, openFile: () -> Unit) {
    val strings = LocalStrings.current.side
    val colors = MaterialTheme.colorScheme
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .combinedClickable(
                onClick = { if (row.dir) actions.toggle(row.path) },
                onDoubleClick = {
                    when {
                        !row.dir -> openFile()
                        row.runs.isNotEmpty() -> actions.startRun(row.runs.first())
                        else -> actions.toggle(row.path)
                    }
                }
            )
            .padding(start = (row.depth * INDENT_DP).dp, top = 2.dp, bottom = 2.dp)
    ) {
        val icon = when {
            !row.dir -> Icons.AutoMirrored.Outlined.InsertDriveFile
            row.expanded -> Icons.Outlined.ExpandMore
            else -> Icons.Outlined.ChevronRight
        }
        Icon(
            icon,
            contentDescription = null,
            tint = colors.onSurfaceVariant,
            modifier = Modifier.padding(end = 4.dp).size(14.dp)
        )
        Text(
            row.name,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f, fill = false)
        )
        row.change?.let {
            Text(
                it.trim(),
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                color = colors.tertiary,
                modifier = Modifier.padding(start = 6.dp)
            )
        }
        row.runs.forEach { name -> SideBadge(strings.runBadge) { actions.startRun(name) } }
    }
}

private const val INDENT_DP = 12
