package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import madang.api.model.Issue
import madang.api.model.MemoryLayer
import madang.shared.main.MemoryDraft
import madang.shared.main.MemoryState

/** 메모리 패널 조작. */
class MemoryActions(
    val select: (MemoryLayer) -> Unit,
    val edit: (String) -> Unit,
    val save: () -> Unit,
    val close: () -> Unit,
    val onEditing: (Boolean) -> Unit
)

/**
 * 3열 오른쪽 메모리 패널: root / space / state 탭, 원문 편집기, 토큰 수, 저장.
 *
 * core 검사기가 거부하면 문제가 있는 줄을 붉게 칠하고 그 줄 오른쪽에 이유를 붙인다. 줄을
 * 가리키지 않는 문제는 편집기 위에 보인다.
 */
@Composable
fun MemoryPanel(state: MemoryState, actions: MemoryActions, modifier: Modifier) {
    val strings = LocalStrings.current.page
    Column(modifier = modifier.background(MaterialTheme.colorScheme.surfaceContainerLow)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp, top = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                strings.memory,
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.weight(1f)
            )
            ToolbarIcon(Icons.Outlined.Close, strings.close, actions.close)
        }
        Row(
            modifier = Modifier.padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            MemoryLayer.entries.forEach { layer ->
                val dirty = state.drafts[layer]?.dirty == true
                FilterChip(
                    selected = state.layer == layer,
                    onClick = { actions.select(layer) },
                    label = { Text(strings.memoryLayer(layer) + if (dirty) " •" else "") }
                )
            }
        }
        state.error?.let { ErrorLine(it) }
        val draft = state.current
        if (draft == null) {
            Text(
                strings.memoryLoading,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(12.dp)
            )
            return@Column
        }
        DraftHeader(draft, actions.save)
        draft.fileIssues.forEach { ErrorLine(it.message) }
        HorizontalDivider()
        MemoryEditor(draft, actions, Modifier.weight(1f).fillMaxWidth())
    }
}

@Composable
private fun DraftHeader(draft: MemoryDraft, onSave: () -> Unit) {
    val strings = LocalStrings.current.page
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                draft.file.path,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            val status = when {
                draft.issues.isNotEmpty() -> strings.memoryRejected(draft.issues.size)
                draft.saved -> strings.memorySaved
                else -> strings.memoryTokens(draft.file.tokens, draft.file.tokenLimit)
            }
            Text(
                status,
                style = MaterialTheme.typography.labelSmall,
                color = if (draft.issues.isNotEmpty()) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                }
            )
        }
        Button(onClick = onSave, enabled = draft.dirty && !draft.saving) {
            Text(LocalStrings.current.save)
        }
    }
}

@Composable
private fun ErrorLine(message: String) {
    Text(
        message,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.error,
        modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp)
    )
}

/** 줄 번호가 붙은 원문 편집기. 줄바꿈 없이 가로로 스크롤해서 논리 줄과 화면 줄을 맞춘다. */
@Composable
private fun MemoryEditor(draft: MemoryDraft, actions: MemoryActions, modifier: Modifier) {
    val strings = LocalStrings.current.page
    val errorColor = MaterialTheme.colorScheme.errorContainer
    val textStyle = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontSize = 12.sp,
        lineHeight = 18.sp,
        color = MaterialTheme.colorScheme.onSurface
    )
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    val byLine = draft.issuesByLine
    val lineTops = lineTops(draft.text, layout)
    val density = LocalDensity.current
    Box(modifier = modifier.verticalScroll(rememberScrollState())) {
        Row(modifier = Modifier.padding(vertical = 8.dp)) {
            LineGutter(lineTops, byLine.keys, textStyle)
            Box(modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState())) {
                BasicTextField(
                    value = draft.text,
                    onValueChange = actions.edit,
                    textStyle = textStyle,
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    onTextLayout = { layout = it },
                    modifier = Modifier
                        .widthIn(min = 320.dp)
                        .padding(end = 12.dp)
                        .onFocusChanged { actions.onEditing(it.isFocused) }
                        .drawBehind {
                            val result = layout ?: return@drawBehind
                            byLine.keys.forEach { line ->
                                val top = lineTops.getOrNull(line - 1) ?: return@forEach
                                val bottom =
                                    result.getLineBottom(result.getLineForVerticalPosition(top))
                                drawRect(
                                    errorColor,
                                    topLeft = Offset(0f, top),
                                    size = Size(size.width, bottom - top)
                                )
                            }
                        }
                )
            }
        }
        byLine.forEach { (line, issues) ->
            val top = lineTops.getOrNull(line - 1) ?: return@forEach
            LineIssue(
                strings.lineLabel(line),
                issues,
                Modifier.align(Alignment.TopEnd)
                    .offset(y = with(density) { top.toDp() } + 8.dp)
                    .padding(end = 8.dp)
            )
        }
    }
}

/** 논리 줄(1부터)마다 그 줄이 시작하는 y 위치. 아직 그리기 전이면 비어 있다. */
private fun lineTops(text: String, layout: TextLayoutResult?): List<Float> {
    if (layout == null || layout.layoutInput.text.text != text) return emptyList()
    var offset = 0
    return text.split('\n').map { line ->
        val top = layout.getLineTop(layout.getLineForOffset(offset))
        offset += line.length + 1
        top
    }
}

@Composable
private fun LineGutter(lineTops: List<Float>, errorLines: Set<Int>, style: TextStyle) {
    val density = LocalDensity.current
    Box(modifier = Modifier.width(40.dp)) {
        lineTops.forEachIndexed { index, top ->
            val line = index + 1
            val error = line in errorLines
            Text(
                "$line",
                style = style.copy(
                    color = if (error) {
                        MaterialTheme.colorScheme.error
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    }
                ),
                modifier = Modifier.offset(y = with(density) { top.toDp() })
                    .padding(start = 8.dp)
            )
        }
    }
}

@Composable
private fun LineIssue(label: String, issues: List<Issue>, modifier: Modifier) {
    Text(
        "$label · " + issues.joinToString(" / ") { it.message },
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onError,
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
        modifier = modifier
            .widthIn(max = 260.dp)
            .background(
                MaterialTheme.colorScheme.error.copy(alpha = 0.9f),
                RoundedCornerShape(4.dp)
            )
            .padding(horizontal = 6.dp, vertical = 1.dp)
    )
}
