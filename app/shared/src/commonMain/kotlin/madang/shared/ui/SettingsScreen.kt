package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import madang.shared.settings.Language
import madang.shared.settings.RoutesStatus
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
        RoutesSection(state, viewModel)
        HorizontalDivider()
        RunnersSection(state, viewModel::refreshRunners)
        HorizontalDivider()
        LanguageSection(state.language, viewModel::setLanguage)
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

@Composable
private fun RoutesSection(state: SettingsState, viewModel: SettingsViewModel) {
    val strings = LocalStrings.current
    Section(strings.routesTitle) {
        OutlinedTextField(
            value = state.routesText,
            onValueChange = viewModel::setRoutesText,
            enabled = state.routesStatus != RoutesStatus.Loading,
            textStyle = TextStyle(fontFamily = FontFamily.Monospace),
            modifier = Modifier.fillMaxWidth().heightIn(min = 240.dp)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = viewModel::saveRoutes,
                enabled = state.routesStatus == RoutesStatus.Editing ||
                    state.routesStatus is RoutesStatus.Invalid
            ) { Text(strings.save) }
            OutlinedButton(onClick = viewModel::loadRoutes) { Text(strings.reload) }
        }
        RoutesStatusLine(state.routesStatus)
    }
}

@Composable
private fun RoutesStatusLine(status: RoutesStatus) {
    val strings = LocalStrings.current
    val error = MaterialTheme.colorScheme.error
    when (status) {
        RoutesStatus.Loading, RoutesStatus.Editing -> Unit

        RoutesStatus.Saving -> Text(strings.saving)

        RoutesStatus.Saved -> Text(strings.saved, color = MaterialTheme.colorScheme.primary)

        is RoutesStatus.Error -> Text(status.message, color = error)

        is RoutesStatus.Invalid -> {
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
private fun Section(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        content()
    }
}
