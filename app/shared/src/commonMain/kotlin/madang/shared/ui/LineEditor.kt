package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
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

/**
 * 줄 번호가 붙은 원문 편집기. 줄바꿈 없이 가로로 스크롤해서 논리 줄과 화면 줄을 맞춘다.
 *
 * [issuesByLine]의 줄(1부터)은 붉게 칠하고 그 줄 오른쪽에 이유를 붙인다. 세로 스크롤은 부르는
 * 쪽이 맡는다(내용만큼 자란다).
 */
@Composable
fun LineEditor(
    text: String,
    issuesByLine: Map<Int, List<Issue>>,
    onEdit: (String) -> Unit,
    onEditing: (Boolean) -> Unit,
    modifier: Modifier = Modifier
) {
    val strings = LocalStrings.current.page
    val errorColor = MaterialTheme.colorScheme.errorContainer
    val textStyle = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontSize = 12.sp,
        lineHeight = 18.sp,
        color = MaterialTheme.colorScheme.onSurface
    )
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    val lineTops = lineTops(text, layout)
    val density = LocalDensity.current
    Box(modifier = modifier) {
        Row(modifier = Modifier.padding(vertical = 8.dp)) {
            LineGutter(lineTops, issuesByLine.keys, textStyle)
            Box(modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState())) {
                BasicTextField(
                    value = text,
                    onValueChange = onEdit,
                    textStyle = textStyle,
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    onTextLayout = { layout = it },
                    modifier = Modifier
                        .widthIn(min = 320.dp)
                        .padding(end = 12.dp)
                        .onFocusChanged { onEditing(it.isFocused) }
                        .drawBehind {
                            val result = layout ?: return@drawBehind
                            issuesByLine.keys.forEach { line ->
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
        issuesByLine.forEach { (line, issues) ->
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
