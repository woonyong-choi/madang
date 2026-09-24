package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.PageCard
import madang.api.model.Project
import madang.shared.main.searchPages

/** 페이지 검색(Cmd/Ctrl+K). 위아래로 고르고 Enter나 클릭으로 연다. */
@Composable
fun SearchDialog(
    cards: List<PageCard>,
    projects: List<Project>,
    onOpen: (PageCard) -> Unit,
    onDismiss: () -> Unit
) {
    val strings = LocalStrings.current.page
    var query by remember { mutableStateOf("") }
    var selected by remember { mutableIntStateOf(0) }
    val results = searchPages(cards, query)
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }
    val open = { card: PageCard ->
        onDismiss()
        onOpen(card)
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(strings.searchTitle) },
        text = {
            Column(modifier = Modifier.widthIn(min = 420.dp, max = 560.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = {
                        query = it
                        selected = 0
                    },
                    placeholder = { Text(strings.searchPlaceholder) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().focusRequester(focus)
                        .onPreviewKeyEvent { event ->
                            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                            when (event.key) {
                                Key.DirectionDown ->
                                    selected =
                                        (selected + 1).coerceAtMost(results.lastIndex)

                                Key.DirectionUp -> selected = (selected - 1).coerceAtLeast(0)

                                Key.Enter, Key.NumPadEnter ->
                                    results.getOrNull(selected)?.let(open)

                                else -> return@onPreviewKeyEvent false
                            }
                            true
                        }
                )
                if (results.isEmpty()) {
                    Text(strings.searchEmpty, modifier = Modifier.padding(top = 12.dp))
                }
                LazyColumn(modifier = Modifier.heightIn(max = 360.dp).padding(top = 8.dp)) {
                    itemsIndexed(results, key = { _, card -> card.id }) { index, card ->
                        val project = projects.firstOrNull { it.id == card.project }?.title
                        SearchRow(card, project ?: card.project, index == selected) { open(card) }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text(strings.close) } }
    )
}

@Composable
private fun SearchRow(card: PageCard, project: String, selected: Boolean, onClick: () -> Unit) {
    val background =
        if (selected) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent
    Row(
        modifier = Modifier.fillMaxWidth()
            .background(background, RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(card.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
            card.preview?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
        Text(
            project,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.tertiary,
            modifier = Modifier.padding(start = 8.dp)
        )
    }
}
