package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import madang.shared.onboarding.OnboardingState
import madang.shared.onboarding.OnboardingStep
import madang.shared.onboarding.OnboardingViewModel

/** 권한 규칙 제안 문구. 파일은 바꾸지 않고 보여 주기만 한다. */
private val PermissionSuggestions = """
    Claude — ~/.claude/settings.json
      permissions.allow: ["Bash(madang *)"]
      permissions.deny:  ["Bash(git push *)", "Bash(rm -rf *)"]

    Codex — ~/.codex/rules/madang.rules
      prefix_rule(["madang"], "allow")
""".trimIndent()

@Composable
fun OnboardingScreen(viewModel: OnboardingViewModel) {
    val state by viewModel.state.collectAsState()
    val strings = LocalStrings.current
    Box(modifier = Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
        Column(
            modifier = Modifier.widthIn(max = 640.dp).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(strings.onboardingTitle, style = MaterialTheme.typography.headlineMedium)
            Text(
                "${state.step.ordinal + 1} / ${OnboardingStep.entries.size}",
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            when (state.step) {
                OnboardingStep.HOME -> HomeStep(state, viewModel::setHomePath)
                OnboardingStep.REMOTE -> RemoteStep(state, viewModel::setRemote)
                OnboardingStep.TOOLS -> ToolsStep(state)
                OnboardingStep.PERMISSIONS -> PermissionsStep()
            }
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Navigation(state, viewModel)
        }
    }
}

@Composable
private fun HomeStep(state: OnboardingState, onChange: (String) -> Unit) {
    val strings = LocalStrings.current
    StepHeader(strings.homeStepTitle, strings.homeStepBody)
    OutlinedTextField(
        value = state.homePath,
        onValueChange = onChange,
        singleLine = true,
        modifier = Modifier.fillMaxWidth()
    )
}

@Composable
private fun RemoteStep(state: OnboardingState, onChange: (String) -> Unit) {
    val strings = LocalStrings.current
    StepHeader(strings.remoteStepTitle, strings.remoteStepBody)
    OutlinedTextField(
        value = state.remote,
        onValueChange = onChange,
        singleLine = true,
        isError = state.remoteInvalid,
        placeholder = { Text("git@github.com:me/madang-home.git") },
        supportingText = if (state.remoteInvalid) {
            { Text(strings.remoteInvalid) }
        } else {
            null
        },
        modifier = Modifier.fillMaxWidth()
    )
}

@Composable
private fun ToolsStep(state: OnboardingState) {
    val strings = LocalStrings.current
    StepHeader(strings.toolsStepTitle, strings.toolsStepBody)
    for (tool in state.tools) {
        val status = tool.status
        val detail = when {
            status == null -> strings.checking
            status.installed -> listOfNotNull(status.version, status.path).joinToString(" · ")
            else -> strings.notInstalled + (status.error?.let { " ($it)" } ?: "")
        }
        LabeledValue(tool.name, detail)
    }
    if (state.runners.isNotEmpty()) {
        Text(strings.coreRunners, style = MaterialTheme.typography.titleSmall)
        for (runner in state.runners) {
            val availability = if (runner.available) strings.available else strings.unavailable
            LabeledValue(runner.name, availability + (runner.reason?.let { " — $it" } ?: ""))
        }
    }
}

@Composable
private fun PermissionsStep() {
    val strings = LocalStrings.current
    StepHeader(strings.permissionsStepTitle, strings.permissionsStepBody)
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier.fillMaxWidth()
    ) {
        SelectionContainer {
            Text(
                PermissionSuggestions,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(12.dp)
            )
        }
    }
    Text(strings.permissionsNote, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun Navigation(state: OnboardingState, viewModel: OnboardingViewModel) {
    val strings = LocalStrings.current
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.step != OnboardingStep.HOME) {
            OutlinedButton(onClick = viewModel::back, enabled = !state.submitting) {
                Text(strings.back)
            }
        }
        if (state.step == OnboardingStep.PERMISSIONS) {
            TextButton(onClick = viewModel::later, enabled = !state.submitting) {
                Text(strings.later)
            }
        } else {
            Button(onClick = viewModel::next, enabled = state.canGoNext) { Text(strings.next) }
        }
    }
}

@Composable
private fun StepHeader(title: String, body: String) {
    Text(title, style = MaterialTheme.typography.titleLarge)
    Text(body, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
internal fun LabeledValue(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge, modifier = Modifier.widthIn(80.dp))
        Text(value, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
