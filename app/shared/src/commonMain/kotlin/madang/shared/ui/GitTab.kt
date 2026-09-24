package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.GitFile
import madang.shared.main.GitState
import madang.shared.main.GitView
import madang.shared.main.Load
import madang.shared.main.staged
import madang.shared.main.unstaged

/** git 탭 조작. 모두 core에 요청한다. */
class GitActions(
    val setMessage: (String) -> Unit,
    val stage: (List<String>?) -> Unit,
    val commit: () -> Unit,
    val push: () -> Unit,
    val pull: () -> Unit,
    val init: () -> Unit,
    val reload: () -> Unit,
    val onEditing: (Boolean) -> Unit
)

/**
 * 사이드바 git 탭. git 저장소면 변경·스테이지·커밋·브랜치·워크트리(쓰는 페이지)·로그와 푸시/풀,
 * 아니면 "git 시작" 하나만 보인다. 조작은 모두 core가 하고, 앱 밖에서 한 조작은 다시 받을 때
 * 상태로 보일 뿐이다.
 *
 * @param pageTitle 워크트리를 쓰는 페이지 id의 제목.
 */
@Composable
fun GitTab(
    state: GitState,
    actions: GitActions,
    pageTitle: (String) -> String,
    modifier: Modifier
) {
    val strings = LocalStrings.current.side
    Column(modifier = modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        state.error?.let { SideError(it) }
        when (val view = state.view) {
            null -> SideNote(strings.noProject)

            Load.Loading -> SideNote(strings.loading)

            is Load.Failed -> SideError(strings.failed(view.message))

            is Load.Ready -> if (view.value.repository) {
                Repository(view.value, state, actions, pageTitle)
            } else {
                SideNote(strings.gitNotRepository)
                Button(onClick = actions.init, enabled = !state.busy) { Text(strings.gitInit) }
            }
        }
    }
}

@Composable
private fun Repository(
    view: GitView,
    state: GitState,
    actions: GitActions,
    pageTitle: (String) -> String
) {
    val strings = LocalStrings.current.side
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            view.status.branch ?: strings.gitDetached,
            style = MaterialTheme.typography.titleSmall,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        TextButton(onClick = actions.pull, enabled = !state.busy) { Text(strings.gitPull) }
        TextButton(onClick = actions.push, enabled = !state.busy) { Text(strings.gitPush) }
        ToolbarIcon(Icons.Outlined.Refresh, strings.reload, actions.reload)
    }
    Changes(view.status.files, state.busy, actions)
    CommitBox(state, actions)
    HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
    SideHeading(strings.gitBranches)
    view.branches?.branches.orEmpty().forEach { branch ->
        val current = branch == view.branches?.current
        Text(
            (if (current) "* " else "  ") + branch,
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            fontWeight = if (current) FontWeight.SemiBold else FontWeight.Normal
        )
    }
    SideHeading(strings.gitWorktrees, Modifier.padding(top = 8.dp))
    view.worktrees.forEach { worktree ->
        val owner = if (worktree.main) {
            strings.gitWorktreeMain
        } else {
            worktree.page?.let { strings.gitWorktreePage(pageTitle(it)) }
        }
        Column(modifier = Modifier.padding(vertical = 2.dp)) {
            Text(
                worktree.path.substringAfterLast('/'),
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace
            )
            Text(
                listOfNotNull(worktree.branch ?: strings.gitDetached, owner).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
    SideHeading(strings.gitLog, Modifier.padding(top = 8.dp))
    view.log.forEach { entry ->
        Row {
            Text(
                entry.hash.take(SHORT_HASH),
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.tertiary,
                modifier = Modifier.padding(end = 6.dp)
            )
            Text(
                entry.subject,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
private fun Changes(files: List<GitFile>, busy: Boolean, actions: GitActions) {
    val strings = LocalStrings.current.side
    val staged = files.filter { it.staged }
    val unstaged = files.filter { it.unstaged }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 6.dp)) {
        SideHeading(strings.gitChanges, Modifier.weight(1f))
        if (unstaged.isNotEmpty()) {
            TextButton(onClick = { actions.stage(null) }, enabled = !busy) {
                Text(strings.gitStageAll, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
    if (unstaged.isEmpty()) SideNote(strings.gitNoChanges)
    unstaged.forEach { file ->
        FileChange(file) {
            TextButton(
                onClick = { actions.stage(listOf(file.path)) },
                enabled = !busy,
                contentPadding = PaddingValues(horizontal = 6.dp)
            ) { Text(strings.gitStage, style = MaterialTheme.typography.labelSmall) }
        }
    }
    if (staged.isNotEmpty()) {
        SideHeading(strings.gitStaged, Modifier.padding(top = 6.dp))
        staged.forEach { file -> FileChange(file) {} }
    }
}

@Composable
private fun FileChange(file: GitFile, trailing: @Composable () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            file.code.replace(' ', '·'),
            style = MaterialTheme.typography.labelSmall,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.tertiary,
            modifier = Modifier.padding(end = 6.dp)
        )
        Text(
            file.path,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        trailing()
    }
}

@Composable
private fun CommitBox(state: GitState, actions: GitActions) {
    val strings = LocalStrings.current.side
    Column(
        verticalArrangement = Arrangement.spacedBy(6.dp),
        modifier = Modifier.padding(top = 8.dp)
    ) {
        OutlinedTextField(
            value = state.message,
            onValueChange = actions.setMessage,
            placeholder = { Text(strings.gitCommitPlaceholder) },
            textStyle = MaterialTheme.typography.bodySmall,
            minLines = 2,
            modifier = Modifier.fillMaxWidth().onFocusChanged { actions.onEditing(it.isFocused) }
        )
        Row {
            Spacer(Modifier.weight(1f))
            OutlinedButton(
                onClick = actions.commit,
                enabled = !state.busy && state.message.isNotBlank()
            ) { Text(strings.gitCommit) }
        }
    }
}

private const val SHORT_HASH = 7
