package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.TableChart
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
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.mikepenz.markdown.m3.Markdown
import com.mikepenz.markdown.m3.markdownTypography
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.RunRecord
import madang.shared.main.dataPreview
import madang.shared.main.instantOrNull

/** 본문의 블록 하나. 접힌 메시지는 한 줄로 줄고, 클릭하면 펼쳐진다. */
@Composable
fun BlockItem(block: BlockHeader, content: String?, folded: Boolean, onToggle: () -> Unit) {
    when (block.type) {
        BlockType.MESSAGE -> when (block.role) {
            MessageRole.USER -> UserMessage(block.text.orEmpty(), folded, onToggle)
            MessageRole.ROUTER -> RouterMessage(block.text.orEmpty(), folded, onToggle)
            else -> AgentMessage(block.text.orEmpty(), folded, onToggle)
        }

        BlockType.DOC -> DocBlock(block, content)

        BlockType.DATA -> DataBlock(block, content)

        BlockType.VIEW -> ViewBlock(block)

        else -> OtherBlock(block)
    }
}

@Composable
private fun UserMessage(text: String, folded: Boolean, onToggle: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Box(
            modifier = Modifier
                .widthIn(max = 520.dp)
                .background(MaterialTheme.colorScheme.secondaryContainer, RoundedCornerShape(14.dp))
                .clickable(onClick = onToggle)
                .padding(horizontal = 14.dp, vertical = 8.dp)
        ) {
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = if (folded) 1 else Int.MAX_VALUE,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
private fun RouterMessage(text: String, folded: Boolean, onToggle: () -> Unit) {
    val color = MaterialTheme.colorScheme.outline
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        fontFamily = FontFamily.Monospace,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        maxLines = if (folded) 1 else Int.MAX_VALUE,
        overflow = TextOverflow.Ellipsis,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onToggle)
            .drawBehind {
                val y = size.height - 1f
                drawLine(
                    color,
                    Offset(0f, y),
                    Offset(size.width, y),
                    strokeWidth = 1f,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 4f))
                )
            }
            .padding(vertical = 4.dp)
    )
}

@Composable
private fun AgentMessage(text: String, folded: Boolean, onToggle: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().height(IntrinsicSize.Min).clickable(onClick = onToggle)
    ) {
        Box(
            Modifier.width(3.dp).fillMaxHeight()
                .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.5f))
        )
        Box(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
            if (folded) {
                Text(
                    text.lineSequence().firstOrNull().orEmpty(),
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            } else {
                PageMarkdown(text)
            }
        }
    }
}

/** 본문 크기에 맞춘 마크다운. 제목은 본문 열 안에서 과하게 커지지 않게 줄인다. */
@Composable
private fun PageMarkdown(text: String) {
    val type = MaterialTheme.typography
    Markdown(
        content = text,
        typography = markdownTypography(
            h1 = type.titleLarge,
            h2 = type.titleMedium,
            h3 = type.titleSmall,
            h4 = type.titleSmall,
            h5 = type.titleSmall,
            h6 = type.titleSmall,
            text = type.bodyMedium,
            paragraph = type.bodyMedium
        )
    )
}

@Composable
private fun DocBlock(block: BlockHeader, content: String?) {
    val strings = LocalStrings.current.navigator
    var more by remember(block.id) { mutableStateOf(false) }
    val long = (content?.lines()?.size ?: 0) > DOC_LINES_BEFORE_MORE
    BlockFrame(Icons.Outlined.Description, block.title ?: block.file ?: block.id) {
        Box(
            modifier = Modifier.fillMaxWidth()
                .then(if (long && !more) Modifier.heightIn(max = 320.dp) else Modifier)
                .clipToBounds()
        ) {
            PageMarkdown(content.orEmpty())
        }
        if (long) {
            TextButton(onClick = { more = !more }) {
                Text(if (more) strings.showLess else strings.showMore)
            }
        }
    }
}

@Composable
private fun DataBlock(block: BlockHeader, content: String?) {
    val strings = LocalStrings.current.navigator
    val preview = content?.let { dataPreview(it, csv = block.format == BlockHeader.Format.CSV) }
    BlockFrame(Icons.Outlined.TableChart, block.title ?: block.file ?: block.id) {
        if (preview == null) {
            Text(
                content.orEmpty().take(RAW_PREVIEW_CHARS),
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace
            )
            return@BlockFrame
        }
        Column(modifier = Modifier.horizontalScroll(rememberScrollState())) {
            TableRow(preview.columns, header = true)
            preview.rows.forEach { TableRow(it, header = false) }
        }
        Text(
            listOfNotNull(block.file, strings.rows(preview.rowCount)).joinToString(" · "),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 6.dp)
        )
    }
}

@Composable
private fun TableRow(cells: List<String>, header: Boolean) {
    Row {
        for (cell in cells) {
            Text(
                cell,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = if (header) FontWeight.SemiBold else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.width(140.dp)
                    .border(0.5.dp, MaterialTheme.colorScheme.outlineVariant)
                    .padding(horizontal = 6.dp, vertical = 3.dp)
            )
        }
    }
}

@Composable
private fun ViewBlock(block: BlockHeader) {
    val strings = LocalStrings.current.navigator
    BlockFrame(Icons.Outlined.Dashboard, block.title ?: block.id) {
        Box(
            modifier = Modifier.fillMaxWidth().height(120.dp)
                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(6.dp)),
            contentAlignment = Alignment.Center
        ) {
            Text(
                strings.viewPlaceholder,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        block.template?.let {
            Text(
                "${strings.templateLabel} $it",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 6.dp)
            )
        }
    }
}

@Composable
private fun OtherBlock(block: BlockHeader) {
    val strings = LocalStrings.current.navigator
    BlockFrame(Icons.Outlined.Description, block.title ?: block.id) {
        Text(
            listOfNotNull(strings.blockType(block.type), block.path ?: block.cmd ?: block.url)
                .joinToString(" · "),
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
private fun BlockFrame(icon: ImageVector, title: String, content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
            .padding(12.dp)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(bottom = 8.dp)
        ) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                title,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.padding(start = 6.dp)
            )
        }
        content()
    }
}

/** run 한 줄 카드. 펼치면 종류·등급·바뀐 파일·커밋을 보인다. */
@Composable
fun RunItem(run: RunRecord, folded: Boolean, onToggle: () -> Unit) {
    val strings = LocalStrings.current.navigator
    val colors = MaterialTheme.colorScheme
    Column(
        modifier = Modifier.fillMaxWidth()
            .background(colors.surfaceVariant.copy(alpha = 0.6f), RoundedCornerShape(8.dp))
            .clickable(onClick = onToggle)
            .padding(horizontal = 12.dp, vertical = 6.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            RunnerChip("${run.runner.orEmpty()}/${run.model.orEmpty()}")
            Text(
                runSummary(run, strings),
                style = MaterialTheme.typography.labelMedium,
                color = colors.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 8.dp).weight(1f)
            )
            run.resultStatus?.let {
                Text(it.value, style = MaterialTheme.typography.labelSmall, color = colors.primary)
            }
        }
        if (!folded) {
            Column(modifier = Modifier.padding(top = 6.dp)) {
                val meta =
                    listOfNotNull(run.kind, run.tier?.let { "tier $it" }, run.effort, run.commit)
                Text(meta.joinToString(" · "), style = MaterialTheme.typography.labelSmall)
                for (file in run.changedFiles) {
                    Text(
                        file,
                        style = MaterialTheme.typography.labelSmall,
                        fontFamily = FontFamily.Monospace,
                        color = colors.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
fun RunnerChip(label: String) {
    Text(
        label,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onPrimaryContainer,
        modifier = Modifier
            .background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    )
}

/** 입력·출력 토큰, 소요 시간, 바뀐 파일 수. */
fun runSummary(run: RunRecord, strings: NavigatorStrings): String {
    val started = instantOrNull(run.started)
    val finished = instantOrNull(run.finished)
    val seconds = if (started != null &&
        finished != null
    ) {
        (finished - started).inWholeSeconds
    } else {
        null
    }
    return listOfNotNull(
        strings.inputTokens(formatTokens(run.usage.input)),
        strings.outputTokens(formatTokens(run.usage.output)),
        seconds?.let(strings.seconds),
        strings.changedFiles(run.changedFiles.size)
    ).joinToString(" · ")
}

private const val DOC_LINES_BEFORE_MORE = 24
private const val RAW_PREVIEW_CHARS = 600
