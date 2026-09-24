package madang.shared.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.TrashEntry
import madang.shared.main.TrashViewModel

/** 최근 삭제: 지운 페이지·블록 목록과 복구 버튼. 열 때 목록을 새로 받는다. */
@Composable
fun TrashDialog(viewModel: TrashViewModel, onDismiss: () -> Unit) {
    val strings = LocalStrings.current.page
    val state by viewModel.state.collectAsState()
    LaunchedEffect(viewModel) { viewModel.load() }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(strings.recentlyDeleted) },
        text = {
            Column(modifier = Modifier.widthIn(min = 360.dp, max = 560.dp)) {
                state.error?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
                val entries = state.entries
                when {
                    entries == null -> CircularProgressIndicator()

                    entries.isEmpty() -> Text(strings.trashEmpty)

                    else -> LazyColumn(modifier = Modifier.heightIn(max = 420.dp)) {
                        items(entries, key = { it.id }) { entry ->
                            TrashRow(entry, state.restoring) { viewModel.restore(entry.id) }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text(strings.close) } }
    )
}

@Composable
private fun TrashRow(entry: TrashEntry, restoring: String?, onRestore: () -> Unit) {
    val strings = LocalStrings.current.page
    Row(
        modifier = Modifier.padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            val what = entry.block?.let(strings.trashBlock) ?: strings.trashPage
            Text(
                "$what · ${entry.page}",
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                "${entry.deleted.take(DATE_TIME_CHARS).replace('T', ' ')} · ${entry.project}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        if (restoring == entry.id) {
            CircularProgressIndicator(modifier = Modifier.padding(8.dp))
        } else {
            TextButton(onClick = onRestore, enabled = restoring == null) {
                Text(strings.restore)
            }
        }
    }
}

/** `2026-09-23T18:02` 까지. */
private const val DATE_TIME_CHARS = 16
