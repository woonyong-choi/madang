package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.UndoResult
import madang.shared.main.RunOutcome
import madang.shared.main.SettleState

/**
 * 결과 블록: 마지막으로 끝난 run의 자동 머지·게시 상태(대기·완료·거부)와 되돌리기, 다시 실행.
 *
 * 머지·게시는 core 정책이 한다. 여기서 누르는 것은 그 결과를 되감거나 같은 요청을 다시 보내는
 * 것뿐이다. 되돌린 뒤에는 되감은 것을 보인다.
 */
@Composable
fun ResultBar(
    outcome: RunOutcome,
    undoing: Boolean,
    undoResult: UndoResult?,
    onUndo: () -> Unit,
    onRerun: () -> Unit,
    modifier: Modifier = Modifier
) {
    val strings = LocalStrings.current.page
    Row(
        modifier = modifier.fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
            .padding(start = 12.dp, end = 4.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(strings.resultTitle(outcome.n), style = MaterialTheme.typography.labelMedium)
        outcome.settle?.let { SettleChip(outcome, it, Modifier.padding(start = 10.dp)) }
        Text(
            undoText(outcome, undoing, undoResult),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).padding(horizontal = 10.dp)
        )
        if (!outcome.undone) {
            TextButton(onClick = onUndo, enabled = !undoing) { Text(strings.undo) }
        }
        TextButton(onClick = onRerun, enabled = !undoing) { Text(strings.rerun) }
    }
}

/** 되돌리는 중이거나 되돌린 뒤의 한 줄. 아니면 빈 문자열. */
@Composable
private fun undoText(outcome: RunOutcome, undoing: Boolean, result: UndoResult?): String {
    val strings = LocalStrings.current.page
    return when {
        undoing -> strings.undoing
        result != null -> strings.undoSummary(result)
        outcome.undone -> strings.undone
        else -> ""
    }
}

@Composable
private fun SettleChip(outcome: RunOutcome, state: SettleState, modifier: Modifier) {
    val strings = LocalStrings.current.page
    val color = settleColor(state)
    val details = listOfNotNull(
        outcome.merged?.let { strings.merged(it.take(SHORT_HASH)) },
        outcome.published?.let(strings.published)
    )
    Box(
        modifier = modifier
            .background(color.copy(alpha = 0.14f), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 1.dp)
    ) {
        Text(
            (listOf(strings.settleState(state)) + details).joinToString(" · "),
            color = color,
            style = MaterialTheme.typography.labelSmall
        )
    }
}

private fun settleColor(state: SettleState): Color = when (state) {
    SettleState.PENDING -> Color(0xFF6B7280)
    SettleState.DONE -> Color(0xFF15803D)
    SettleState.REFUSED -> Color(0xFFB45309)
}

private const val SHORT_HASH = 7
