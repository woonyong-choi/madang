package madang.shared.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import madang.shared.settings.DocumentStatus
import madang.shared.settings.Language
import madang.shared.settings.SettingsDocument
import madang.shared.settings.SettingsState
import madang.shared.settings.SettingsViewModel

@Composable
fun SettingsScreen(viewModel: SettingsViewModel, onClose: () -> Unit) {
    val state by viewModel.state.collectAsState()
    val strings = LocalStrings.current
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(strings.settings, style = MaterialTheme.typography.headlineMedium)
            TextButton(onClick = onClose) { Text(strings.close) }
        }
        ConnectionSection(state, viewModel)
        HorizontalDivider()
        ConfigSection(state, viewModel)
        HorizontalDivider()
        ProjectConfigSection(state, viewModel)
        HorizontalDivider()
        RoutesSection(state, viewModel)
        HorizontalDivider()
        RunnersSection(state, viewModel::refreshRunners)
        HorizontalDivider()
        LanguageSection(state.language, viewModel::setLanguage)
        HorizontalDivider()
        NotificationsSection(state.notifications, viewModel::setNotifications)
    }
}

@Composable
private fun ConnectionSection(state: SettingsState, viewModel: SettingsViewModel) {
    val strings = LocalStrings.current
    Section(strings.coreAddress) {
        Text("${strings.connectedTo}: ${state.connectedUrl}")
        OutlinedTextField(
            value = state.coreUrl,
            onValueChange = viewModel::setCoreUrl,
            singleLine = true,
            label = { Text(strings.coreAddress) },
            supportingText = { Text(strings.coreAddressHint) },
            modifier = Modifier.widthIn(max = 560.dp).fillMaxWidth()
        )
        OutlinedTextField(
            value = state.coreBinary,
            onValueChange = viewModel::setCoreBinary,
            singleLine = true,
            label = { Text(strings.coreBinary) },
            supportingText = { Text(strings.coreBinaryHint) },
            modifier = Modifier.widthIn(max = 560.dp).fillMaxWidth()
        )
        OutlinedButton(onClick = viewModel::applyConnection) { Text(strings.reconnect) }
    }
}

/** 앱 홈 config.yaml. */
@Composable
private fun ConfigSection(state: SettingsState, viewModel: SettingsViewModel) {
    val strings = LocalStrings.current
    Section(strings.configTitle) {
        Hint(strings.configHint)
        DocumentEditorView(SettingsDocument.CONFIG, state, viewModel)
    }
}

/** 프로젝트를 골라 그 `.madang/config.yaml`을 고친다. */
@Composable
private fun ProjectConfigSection(state: SettingsState, viewModel: SettingsViewModel) {
    val strings = LocalStrings.current
    Section(strings.projectConfigTitle) {
        Hint(strings.projectConfigHint)
        if (state.projects.isEmpty()) {
            Hint(strings.noProjects)
            DocumentStatusLine(state.document(SettingsDocument.PROJECT_CONFIG).status)
            return@Section
        }
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            for (project in state.projects) {
                FilterChip(
                    selected = state.project == project.id,
                    onClick = { viewModel.selectProject(project.id) },
                    label = { Text(project.title) }
                )
            }
        }
        DocumentEditorView(SettingsDocument.PROJECT_CONFIG, state, viewModel)
    }
}

@Composable
private fun RoutesSection(state: SettingsState, viewModel: SettingsViewModel) {
    Section(LocalStrings.current.routesTitle) {
        DocumentEditorView(SettingsDocument.ROUTES, state, viewModel)
    }
}

/** yaml 원문 편집기, 저장·다시 불러오기, 검사 결과. 거부된 줄은 편집기 안에서도 붉게 보인다. */
@Composable
private fun DocumentEditorView(
    document: SettingsDocument,
    state: SettingsState,
    viewModel: SettingsViewModel
) {
    val strings = LocalStrings.current
    val editor = state.document(document)
    LineEditor(
        editor.text,
        editor.issuesByLine,
        onEdit = { viewModel.setText(document, it) },
        onEditing = {},
        modifier = Modifier.fillMaxWidth()
            .heightIn(min = 160.dp)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(4.dp))
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = { viewModel.save(document) }, enabled = editor.canSave) {
            Text(strings.save)
        }
        OutlinedButton(onClick = { viewModel.reload(document) }) { Text(strings.reload) }
    }
    DocumentStatusLine(editor.status)
}

@Composable
private fun Hint(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )
}

@Composable
private fun DocumentStatusLine(status: DocumentStatus) {
    val strings = LocalStrings.current
    val error = MaterialTheme.colorScheme.error
    when (status) {
        DocumentStatus.Loading, DocumentStatus.Editing -> Unit

        DocumentStatus.Saving -> Text(strings.saving)

        DocumentStatus.Saved -> Text(strings.saved, color = MaterialTheme.colorScheme.primary)

        is DocumentStatus.Error -> Text(status.message, color = error)

        is DocumentStatus.Invalid -> {
            Text(strings.invalid, color = error)
            for (issue in status.issues) {
                val where = listOfNotNull(issue.path, issue.line?.let { "line $it" })
                val prefix = if (where.isEmpty()) "" else where.joinToString(":") + " "
                Text("$prefix[${issue.code}] ${issue.message}", color = error)
            }
        }
    }
}

@Composable
private fun RunnersSection(state: SettingsState, onRefresh: () -> Unit) {
    val strings = LocalStrings.current
    Section(strings.runnersTitle) {
        for (runner in state.runners) {
            val availability = if (runner.available) strings.available else strings.unavailable
            val auth = runner.auth?.value?.let { " · $it" } ?: ""
            LabeledValue(runner.name, availability + auth + (runner.reason?.let { " — $it" } ?: ""))
        }
        state.runnersError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        OutlinedButton(onClick = onRefresh) { Text(strings.refresh) }
    }
}

@Composable
private fun LanguageSection(current: Language, onSelect: (Language) -> Unit) {
    Section(LocalStrings.current.languageTitle) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = current == Language.KO,
                onClick = { onSelect(Language.KO) },
                label = { Text("한국어") }
            )
            FilterChip(
                selected = current == Language.EN,
                onClick = { onSelect(Language.EN) },
                label = { Text("English") }
            )
        }
    }
}

@Composable
private fun NotificationsSection(enabled: Boolean, onChange: (Boolean) -> Unit) {
    val strings = LocalStrings.current.side
    Section(strings.notificationsTitle) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(checked = enabled, onCheckedChange = onChange)
            Text(strings.notificationsLabel, modifier = Modifier.padding(start = 12.dp))
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        content()
    }
}
