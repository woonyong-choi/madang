package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import madang.api.model.Issue
import madang.api.model.MemoryLayer
import madang.shared.main.HeaderField
import madang.shared.main.MemoryDraft
import madang.shared.main.MemoryState
import madang.shared.main.placeIssues
import madang.shared.main.splitMemory

/** 메모리 탭 조작. 층마다 따로 고치고 저장한다. */
class MemoryActions(
    val edit: (MemoryLayer, String) -> Unit,
    val editField: (MemoryLayer, key: String, value: String) -> Unit,
    val toggleRaw: (MemoryLayer) -> Unit,
    val save: (MemoryLayer) -> Unit,
    val onEditing: (Boolean) -> Unit
)

/**
 * 사이드바 메모리 탭: Profile / Brief / Ledger를 언제나 이 순서로 위에서 아래로 보인다.
 *
 * 층마다 머리부는 키별 입력 폼, 본문은 원문 그대로 보인다(문서 렌더러가 붙기 전까지). "원문"을
 * 켜면 파일 전체를 줄 번호 편집기로 고친다. core 검사기가 저장을 거부하면 문제를 그 키·본문·줄
 * 옆에 붙인다.
 */
@Composable
fun MemoryTab(state: MemoryState, actions: MemoryActions, modifier: Modifier) {
    val strings = LocalStrings.current.page
    Column(modifier = modifier.verticalScroll(rememberScrollState())) {
        state.error?.let { ErrorLine(it) }
        val message = when {
            !state.isOpen -> strings.memoryNoPage
            state.ordered.isEmpty() -> strings.memoryLoading
            else -> null
        }
        if (message != null) {
            Text(
                message,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(12.dp)
            )
            return@Column
        }
        state.ordered.forEach { draft ->
            MemorySection(draft, draft.file.layer in state.raw, actions)
            HorizontalDivider()
        }
    }
}

@Composable
private fun MemorySection(draft: MemoryDraft, raw: Boolean, actions: MemoryActions) {
    val layer = draft.file.layer
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        SectionHeader(draft, raw, actions)
        if (raw) {
            draft.fileIssues.forEach { ErrorLine(it.message) }
            LineEditor(
                draft.text,
                draft.issuesByLine,
                { actions.edit(layer, it) },
                actions.onEditing,
                Modifier.fillMaxWidth()
            )
        } else {
            val parts = splitMemory(draft.text)
            val placed = placeIssues(parts, draft.issues)
            placed.loose.forEach { ErrorLine(issueText(it)) }
            parts.fields.forEach { field ->
                HeaderInput(
                    field,
                    placed.byField[field.line].orEmpty(),
                    { actions.editField(layer, field.key, it) },
                    actions.onEditing
                )
            }
            BodyText(parts.body)
            placed.body.forEach { ErrorLine(issueText(it)) }
        }
    }
}

/** 층 이름, 파일 경로, 토큰 수 또는 저장 결과, "원문" 토글, 저장. */
@Composable
private fun SectionHeader(draft: MemoryDraft, raw: Boolean, actions: MemoryActions) {
    val strings = LocalStrings.current.page
    val layer = draft.file.layer
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                strings.memoryLayer(layer) + if (draft.dirty) " •" else "",
                style = MaterialTheme.typography.titleSmall
            )
            Text(
                draft.file.path,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
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
        FilterChip(
            selected = raw,
            onClick = { actions.toggleRaw(layer) },
            label = { Text(strings.memoryRaw) }
        )
        TextButton(
            onClick = { actions.save(layer) },
            enabled = draft.dirty && !draft.saving
        ) { Text(LocalStrings.current.save) }
    }
}

/** 머리부 키 하나. 값은 `키:` 뒤의 원문이고, 검사 문제는 입력칸 아래에 붙는다. */
@Composable
private fun HeaderInput(
    field: HeaderField,
    issues: List<Issue>,
    onChange: (String) -> Unit,
    onEditing: (Boolean) -> Unit
) {
    OutlinedTextField(
        value = field.value,
        onValueChange = onChange,
        label = { Text(field.key) },
        textStyle = MONOSPACE,
        isError = issues.isNotEmpty(),
        supportingText = if (issues.isEmpty()) {
            null
        } else {
            { Text(issues.joinToString(" / ") { it.message }) }
        },
        modifier = Modifier.fillMaxWidth()
            .padding(horizontal = 12.dp)
            .onFocusChanged { onEditing(it.isFocused) }
    )
}

/** 본문. 문서 렌더러가 붙기 전까지 원문을 그대로 보인다. 고치려면 "원문"을 켠다. */
@Composable
private fun BodyText(body: String) {
    val strings = LocalStrings.current.page
    SelectionContainer {
        Text(
            body.trim('\n').ifEmpty { strings.memoryEmptyBody },
            style = MONOSPACE.copy(color = MaterialTheme.colorScheme.onSurface),
            modifier = Modifier.fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 4.dp)
                .background(
                    MaterialTheme.colorScheme.surfaceContainerHighest,
                    RoundedCornerShape(6.dp)
                )
                .padding(8.dp)
        )
    }
}

@Composable
private fun issueText(issue: Issue): String {
    val line = issue.line ?: return issue.message
    return "${LocalStrings.current.page.lineLabel(line)} · ${issue.message}"
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

private val MONOSPACE = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontSize = 12.sp,
    lineHeight = 18.sp
)
