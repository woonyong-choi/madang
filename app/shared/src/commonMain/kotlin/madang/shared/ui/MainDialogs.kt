package madang.shared.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import madang.shared.main.ListSource
import madang.shared.main.MainViewModel

/** 레이어 0에서 여는 대화상자. */
sealed interface MainDialog {
    data object NewSpace : MainDialog

    data class RenameSpace(val slug: String, val title: String) : MainDialog

    data class LinkRepo(val slug: String, val repo: String) : MainDialog

    data class DeleteSpace(val slug: String, val title: String) : MainDialog

    data class EditTags(val page: String, val tags: List<String>) : MainDialog

    data class DeletePage(val page: String, val title: String) : MainDialog

    data object Trash : MainDialog

    data object Search : MainDialog
}

@Composable
fun MainDialogView(dialog: MainDialog, viewModel: MainViewModel, onDismiss: () -> Unit) {
    val strings = LocalStrings.current.navigator
    when (dialog) {
        MainDialog.NewSpace -> TextDialog(
            strings.newSpace,
            strings.spaceNameLabel,
            "",
            null,
            onDismiss
        ) {
            viewModel.createSpace(it)
        }

        is MainDialog.RenameSpace ->
            TextDialog(strings.rename, strings.spaceNameLabel, dialog.title, null, onDismiss) {
                viewModel.renameSpace(dialog.slug, it)
            }

        is MainDialog.LinkRepo ->
            TextDialog(strings.linkRepo, strings.repoLabel, dialog.repo, null, onDismiss) {
                viewModel.linkRepo(dialog.slug, it)
            }

        is MainDialog.EditTags -> TextDialog(
            strings.tag,
            strings.tagsLabel,
            dialog.tags.joinToString(", "),
            strings.tagsHint,
            onDismiss,
            allowEmpty = true
        ) { text ->
            viewModel.setTags(dialog.page, parseTags(text))
        }

        is MainDialog.DeleteSpace ->
            ConfirmDialog(strings.deleteSpaceConfirm(dialog.title), onDismiss) {
                viewModel.deleteSpace(dialog.slug)
            }

        is MainDialog.DeletePage ->
            ConfirmDialog(strings.deletePageConfirm(dialog.title), onDismiss) {
                viewModel.deletePage(dialog.page)
            }

        MainDialog.Trash -> TrashDialog(viewModel.trash, onDismiss)

        MainDialog.Search -> {
            val state by viewModel.state.collectAsState()
            SearchDialog(state.cards, state.spaces, onDismiss = onDismiss, onOpen = { card ->
                viewModel.select(ListSource.InSpace(card.space))
                viewModel.openPage(card.id, advance = true)
            })
        }
    }
}

/** 쉼표로 나눈 태그. 앞의 `#`와 공백을 떼고 빈 것은 버린다. */
fun parseTags(text: String): List<String> = text.split(',').map {
    it.trim().removePrefix("#").trim('/')
}.filter { it.isNotEmpty() }.distinct()

@Composable
private fun TextDialog(
    title: String,
    label: String,
    initial: String,
    hint: String?,
    onDismiss: () -> Unit,
    allowEmpty: Boolean = false,
    onConfirm: (String) -> Unit
) {
    val strings = LocalStrings.current.navigator
    var text by remember { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    label = { Text(label) },
                    singleLine = true
                )
                hint?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(
                enabled = allowEmpty || text.isNotBlank(),
                onClick = {
                    onDismiss()
                    onConfirm(text.trim())
                }
            ) { Text(strings.confirm) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(strings.cancel) } }
    )
}

@Composable
private fun ConfirmDialog(message: String, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    val strings = LocalStrings.current.navigator
    AlertDialog(
        onDismissRequest = onDismiss,
        text = { Text(message) },
        confirmButton = {
            TextButton(onClick = {
                onDismiss()
                onConfirm()
            }) { Text(strings.delete, color = MaterialTheme.colorScheme.error) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(strings.cancel) } }
    )
}
