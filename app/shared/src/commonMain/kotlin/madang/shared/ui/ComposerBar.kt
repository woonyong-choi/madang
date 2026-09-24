package madang.shared.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.shared.main.ComposerKey
import madang.shared.main.ComposerState
import madang.shared.main.composerKey

/** 입력창 조작. [onEditing]은 입력창에 키보드 포커스가 들어오고 나갈 때 불린다. */
class ComposerActions(
    val setText: (String) -> Unit,
    val complete: (String) -> Unit,
    val send: () -> Unit,
    val onEditing: (Boolean) -> Unit,
    val onEscape: () -> Unit
)

/**
 * 3열 아래 입력창: 대상("페이지에게"), 문장, 다음 호출 입력 토큰 추정, 보내기.
 *
 * Enter와 Cmd/Ctrl+Enter로 보내고 Shift+Enter로 줄을 바꾼다. 첫 단어가 종류 이름의 앞부분이면
 * 접두어 후보가 뜨고 Tab이나 클릭으로 채운다.
 */
@Composable
fun ComposerBar(state: ComposerState, actions: ComposerActions, modifier: Modifier = Modifier) {
    val strings = LocalStrings.current.page
    var field by remember(state.page) { mutableStateOf(TextFieldValue(state.text)) }
    if (field.text != state.text) {
        field = TextFieldValue(state.text, TextRange(state.text.length))
    }
    val suggestions = state.suggestions
    Column(modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
        if (suggestions.isNotEmpty()) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 6.dp)
            ) {
                suggestions.forEach { prefix ->
                    AssistChip(onClick = { actions.complete(prefix) }, label = { Text(prefix) })
                }
                Text(
                    strings.completeHint,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth()
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
                .padding(start = 12.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.Bottom
        ) {
            Text(
                strings.toPage,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(end = 10.dp, bottom = 8.dp)
            )
            Box(modifier = Modifier.weight(1f).padding(vertical = 8.dp)) {
                if (field.text.isEmpty()) {
                    Text(
                        strings.inputPlaceholder,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                BasicTextField(
                    value = field,
                    onValueChange = {
                        field = it
                        actions.setText(it.text)
                    },
                    textStyle = MaterialTheme.typography.bodyMedium.copy(
                        color = MaterialTheme.colorScheme.onSurface
                    ),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    modifier = Modifier.fillMaxWidth()
                        .heightIn(max = 180.dp)
                        .onFocusChanged { actions.onEditing(it.isFocused) }
                        .onPreviewKeyEvent { event ->
                            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                            if (event.key == Key.Escape) {
                                actions.onEscape()
                                return@onPreviewKeyEvent true
                            }
                            val key = composerKey(
                                enter = event.key == Key.Enter || event.key == Key.NumPadEnter,
                                tab = event.key == Key.Tab,
                                shift = event.isShiftPressed,
                                hasSuggestions = suggestions.isNotEmpty()
                            )
                            when (key) {
                                ComposerKey.SEND -> actions.send()

                                ComposerKey.COMPLETE -> actions.complete(suggestions.first())

                                ComposerKey.NEWLINE -> {
                                    field = field.withNewline()
                                    actions.setText(field.text)
                                }

                                null -> Unit
                            }
                            key != null
                        }
                )
            }
            state.preview?.let {
                Text(
                    strings.nextInput(formatTokens(it.totalEst), "${it.runner}/${it.model}"),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 10.dp)
                )
            }
            Button(onClick = actions.send, enabled = state.canSend) { Text(strings.send) }
        }
    }
}

/** 선택 영역을 줄바꿈 하나로 바꾼다. */
private fun TextFieldValue.withNewline(): TextFieldValue {
    val start = selection.min
    val next = text.replaceRange(start, selection.max, "\n")
    return TextFieldValue(next, TextRange(start + 1))
}
