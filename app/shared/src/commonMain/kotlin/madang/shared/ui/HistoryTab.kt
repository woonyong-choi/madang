package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.PageDetail
import madang.shared.main.HistoryRow
import madang.shared.main.historyRows

/**
 * 사이드바 기록 탭: 열린 페이지의 run, 최근 것부터. 줄마다 모델·고른 이유(router 메시지)·토큰·
 * 결과를 보이고, 누르면 그 run 탭을 연다.
 */
@Composable
fun HistoryTab(page: PageDetail?, openRun: (Int) -> Unit, modifier: Modifier) {
    val strings = LocalStrings.current.side
    Column(modifier = modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        if (page == null) {
            SideNote(strings.historyNoPage)
            return@Column
        }
        val rows = historyRows(page)
        if (rows.isEmpty()) SideNote(strings.historyEmpty)
        rows.forEach { row -> HistoryLine(row) { openRun(row.n) } }
    }
}

@Composable
private fun HistoryLine(row: HistoryRow, onOpen: () -> Unit) {
    val strings = LocalStrings.current.side
    val colors = MaterialTheme.colorScheme
    val run = row.run
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp)
            .background(colors.surfaceContainerLow, RoundedCornerShape(6.dp))
            .clickable(onClick = onOpen)
            .padding(horizontal = 8.dp, vertical = 6.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusGlyph(row.glyph, Modifier.padding(end = 8.dp))
            Text(
                "run ${row.n}",
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.padding(end = 8.dp)
            )
            RunnerChip("${run.runner.orEmpty()}/${run.model.orEmpty()}")
            Spacer(Modifier.weight(1f))
            run.resultStatus?.let {
                Text(it.value, style = MaterialTheme.typography.labelSmall, color = colors.primary)
            }
        }
        row.reason?.let {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 22.dp, top = 2.dp)
            )
        }
        Text(
            strings.historyCost(formatTokens(run.usage.input), formatTokens(run.usage.output)),
            style = MaterialTheme.typography.labelSmall,
            color = colors.onSurfaceVariant,
            modifier = Modifier.padding(start = 22.dp)
        )
    }
}
