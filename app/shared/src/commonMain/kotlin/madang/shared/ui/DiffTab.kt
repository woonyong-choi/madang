package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.KeyboardArrowDown
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.shared.main.DiffFile
import madang.shared.main.DiffLine
import madang.shared.main.DiffView
import madang.shared.main.Load

/**
 * 디프 탭. core가 준 페이지 작업 폴더의 diff를 파일별로 보인다. 파일 머리를 누르면 접고 펼친다.
 * 서랍에는 파일 목록과 더한·뺀 줄 수가 있다.
 */
@Composable
fun DiffTab(diff: Load<DiffView>?, actions: TabActions, modifier: Modifier) {
    val strings = LocalStrings.current.tabs
    var folded by remember { mutableStateOf(emptySet<String>()) }
    val toggle = { path: String -> folded = if (path in folded) folded - path else folded + path }
    val view = (diff as? Load.Ready)?.value
    TabFrame(
        modifier,
        actions,
        main = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    view?.let { diffSummary(it.files, strings) }.orEmpty(),
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.weight(1f)
                )
                TextButton(onClick = actions.reloadDiff) { Text(strings.reload) }
            }
            when {
                diff == null || diff is Load.Loading -> Placeholder(strings.loading)

                diff is Load.Failed -> Placeholder(diff.message.orEmpty())

                view == null -> Unit

                !view.repository -> Placeholder(strings.noRepository)

                view.files.isEmpty() -> Placeholder(strings.noChanges)

                else -> view.files.forEach {
                    DiffFileView(it, it.path !in folded) { toggle(it.path) }
                }
            }
        },
        drawer = {
            DrawerSection(strings.changedFiles)
            view?.files?.forEach { file ->
                Row(
                    modifier = Modifier.fillMaxWidth().clickable { toggle(file.path) },
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        file.path,
                        style = MaterialTheme.typography.labelMedium,
                        fontFamily = FontFamily.Monospace,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    Counts(file)
                }
            }
        }
    )
}

private fun diffSummary(files: List<DiffFile>, strings: TabStrings): String =
    strings.diffSummary(files.size, files.sumOf { it.added }, files.sumOf { it.removed })

/** 파일 하나: 머리(바뀐 종류·경로·줄 수)와 펼쳤을 때의 줄들. */
@Composable
private fun DiffFileView(file: DiffFile, open: Boolean, toggle: () -> Unit) {
    val strings = LocalStrings.current.tabs
    val colors = MaterialTheme.colorScheme
    Column(modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth()
                .background(colors.surfaceVariant, RoundedCornerShape(6.dp))
                .clickable(onClick = toggle)
                .padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                if (open) {
                    Icons.Outlined.KeyboardArrowDown
                } else {
                    Icons.AutoMirrored.Outlined.KeyboardArrowRight
                },
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = colors.onSurfaceVariant
            )
            Text(
                strings.change(file.change),
                style = MaterialTheme.typography.labelSmall,
                color = colors.primary,
                modifier = Modifier.padding(start = 4.dp, end = 8.dp)
            )
            Text(
                file.path,
                style = MaterialTheme.typography.labelLarge,
                fontFamily = FontFamily.Monospace,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f)
            )
            Counts(file)
        }
        file.oldPath?.let {
            Text(
                strings.renamedFrom(it),
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant,
                modifier = Modifier.padding(start = 28.dp, top = 2.dp)
            )
        }
        if (!open) return@Column
        if (file.binary) {
            Text(
                strings.binaryFile,
                style = MaterialTheme.typography.labelMedium,
                color = colors.onSurfaceVariant,
                modifier = Modifier.padding(8.dp)
            )
        }
        Column(modifier = Modifier.horizontalScroll(rememberScrollState())) {
            file.lines.forEach { DiffLineView(it) }
        }
    }
}

@Composable
private fun DiffLineView(line: DiffLine) {
    val colors = MaterialTheme.colorScheme
    val background = when (line.kind) {
        DiffLine.Kind.ADDED -> ADDED_BACKGROUND
        DiffLine.Kind.REMOVED -> REMOVED_BACKGROUND
        DiffLine.Kind.HUNK -> colors.surfaceVariant.copy(alpha = 0.5f)
        DiffLine.Kind.CONTEXT, DiffLine.Kind.NOTE -> Color.Transparent
    }
    val marker = when (line.kind) {
        DiffLine.Kind.ADDED -> "+"
        DiffLine.Kind.REMOVED -> "-"
        else -> " "
    }
    Row(modifier = Modifier.background(background)) {
        LineNumber(line.oldLine)
        LineNumber(line.newLine)
        Text(
            if (line.kind == DiffLine.Kind.HUNK || line.kind == DiffLine.Kind.NOTE) {
                line.text
            } else {
                "$marker ${line.text}"
            },
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            color = if (line.kind ==
                DiffLine.Kind.HUNK
            ) {
                colors.onSurfaceVariant
            } else {
                colors.onSurface
            },
            softWrap = false,
            modifier = Modifier.padding(start = 8.dp, end = 16.dp)
        )
    }
}

@Composable
private fun LineNumber(number: Int?) {
    Text(
        number?.toString().orEmpty(),
        style = MaterialTheme.typography.bodySmall,
        fontFamily = FontFamily.Monospace,
        color = MaterialTheme.colorScheme.outline,
        modifier = Modifier.width(LINE_NUMBER_WIDTH).padding(end = 6.dp)
    )
}

@Composable
private fun Counts(file: DiffFile) {
    Text(
        "+${file.added}",
        style = MaterialTheme.typography.labelMedium,
        color = ADDED_TEXT,
        modifier = Modifier.padding(start = 8.dp)
    )
    Text(
        "−${file.removed}",
        style = MaterialTheme.typography.labelMedium,
        color = REMOVED_TEXT,
        modifier = Modifier.padding(start = 6.dp)
    )
}

private val LINE_NUMBER_WIDTH = 40.dp
private val ADDED_BACKGROUND = Color(0x3334A853)
private val REMOVED_BACKGROUND = Color(0x33D93025)
private val ADDED_TEXT = Color(0xFF1E7E34)
private val REMOVED_TEXT = Color(0xFFC5221F)
