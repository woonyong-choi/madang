package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.FlowWaitingData
import madang.api.model.PendingDecision
import madang.api.model.Question
import madang.api.model.UnknownFile
import madang.api.model.UnknownFileAction

/** 제목 아래 노란 띠. 누르면 미등록 파일 목록이 열린다. */
@Composable
fun UnknownFilesBand(count: Int, onClick: () -> Unit) {
    Text(
        LocalStrings.current.navigator.unknownFiles(count),
        style = MaterialTheme.typography.labelMedium,
        color = BAND_TEXT,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .background(BAND_BACKGROUND, RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp)
    )
}

/** 미등록 파일 목록. 파일마다 산출물로 / 유지 / 삭제. */
@Composable
fun UnknownFilesDialog(
    files: List<UnknownFile>,
    onResolve: (String, UnknownFileAction.Action) -> Unit,
    onDismiss: () -> Unit
) {
    val strings = LocalStrings.current.page
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(strings.unknownFilesTitle) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                files.forEach { file -> UnknownFileRow(file, onResolve) }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text(strings.close) } }
    )
}

@Composable
private fun UnknownFileRow(
    file: UnknownFile,
    onResolve: (String, UnknownFileAction.Action) -> Unit
) {
    val strings = LocalStrings.current.page
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                file.path,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false)
            )
            file.run?.let {
                Text(
                    strings.unknownFileRun(it),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(start = 8.dp)
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            UnknownFileAction.Action.entries.forEach { action ->
                TextButton(onClick = { onResolve(file.path, action) }) {
                    Text(
                        strings.unknownFileAction(action),
                        color = if (action == UnknownFileAction.Action.DELETE) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.primary
                        }
                    )
                }
            }
        }
    }
}

/**
 * 페이지 상단의 사람 결정 카드. 질문과 선택지를 보이고, 고르면 [onAnswer]로 답을 보낸다.
 * 정책이 머지·게시를 멈춘 묻는 블록이면 거부 이유도 보인다. 결정 없이 멈춘 이유만 있으면
 * (`no_runner` 등) 그 이유를 보인다.
 */
@Composable
fun DecisionCard(waiting: FlowWaitingData, answered: Boolean, onAnswer: (String) -> Unit) {
    val strings = LocalStrings.current.page
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .border(1.dp, MaterialTheme.colorScheme.tertiary, RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.tertiaryContainer, RoundedCornerShape(8.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        val decision = waiting.decision
        Text(
            if (decision?.ask != null) strings.askTitle else strings.decisionTitle,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onTertiaryContainer
        )
        if (decision == null) {
            Text(strings.waitingReason(waiting.reason.orEmpty()))
            return@Column
        }
        Text(decision.question.prompt, style = MaterialTheme.typography.bodyMedium)
        decision.reasons.orEmpty().forEach {
            Text("- $it", style = MaterialTheme.typography.bodySmall)
        }
        if (answered) {
            Text(
                strings.decisionSent,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        } else {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                choices(decision).forEach { (value, label) ->
                    OutlinedButton(onClick = { onAnswer(value) }) { Text(label) }
                }
            }
        }
    }
}

/** 질문 종류별 선택지: (보낼 값, 보일 이름). */
@Composable
private fun choices(decision: PendingDecision): List<Pair<String, String>> {
    val strings = LocalStrings.current.page
    return when (decision.question.kind) {
        Question.Kind.CHOICE -> decision.question.options.orEmpty().map { it to strings.choice(it) }
        Question.Kind.YESNO -> listOf("true" to strings.yes, "false" to strings.no)
        Question.Kind.SCORE -> (1..5).map { "$it" to "$it" }
    }
}

private val BAND_TEXT = Color(0xFF713F12)
private val BAND_BACKGROUND = Color(0xFFFEF3C7)
