package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.RunRecord
import madang.shared.main.instantOrNull

@Composable
fun TableRow(cells: List<String>, header: Boolean) {
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
