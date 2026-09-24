package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import madang.shared.LocalFolderPicker
import madang.shared.onboarding.ClaudeStatus
import madang.shared.onboarding.OnboardingState
import madang.shared.onboarding.OnboardingStep
import madang.shared.onboarding.OnboardingViewModel

/** 첫 실행: 전역 설정 초기화 → 첫 프로젝트 폴더 → claude 확인. */
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
                OnboardingStep.HOME -> HomeStep(state, viewModel)
                OnboardingStep.PROJECT -> ProjectStep(state, viewModel)
                OnboardingStep.CLAUDE -> ClaudeStep(state, viewModel)
            }
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun HomeStep(state: OnboardingState, viewModel: OnboardingViewModel) {
    val strings = LocalStrings.current
    StepHeader(strings.homeStepTitle, strings.homeStepBody)
    LabeledValue(strings.homeLabel, state.homePath)
    if (state.submitting) {
        CircularProgressIndicator()
    } else if (state.error != null) {
        Button(onClick = viewModel::start) { Text(strings.retry) }
    }
}

@Composable
private fun ProjectStep(state: OnboardingState, viewModel: OnboardingViewModel) {
    val strings = LocalStrings.current
    val picker = LocalFolderPicker.current
    val scope = rememberCoroutineScope()
    StepHeader(strings.projectStepTitle, strings.projectStepBody)
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        OutlinedTextField(
            value = state.projectPath,
            onValueChange = viewModel::setProjectPath,
            singleLine = true,
            placeholder = { Text("~/src/my-project") },
            modifier = Modifier.weight(1f)
        )
        OutlinedButton(onClick = {
            scope.launch {
                picker.pick(strings.navigator.chooseProjectFolder)?.let(viewModel::setProjectPath)
            }
        }) { Text(strings.chooseFolder) }
    }
    Button(onClick = viewModel::registerProject, enabled = state.canRegisterProject) {
        Text(strings.next)
    }
}

@Composable
private fun ClaudeStep(state: OnboardingState, viewModel: OnboardingViewModel) {
    val strings = LocalStrings.current
    StepHeader(strings.claudeStepTitle, strings.claudeStepBody)
    LabeledValue("claude", claudeText(state.claude))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = viewModel::checkClaude, enabled = state.claude != null) {
            Text(strings.recheck)
        }
        Button(onClick = viewModel::finish, enabled = !state.done) { Text(strings.begin) }
    }
}

@Composable
private fun claudeText(status: ClaudeStatus?): String {
    val strings = LocalStrings.current
    return when {
        status == null -> strings.checking
        !status.installed -> strings.notInstalled + (status.error?.let { " ($it)" } ?: "")
        status.loggedIn -> strings.claudeLoggedIn(status.authMethod)
        else -> strings.claudeLoggedOut
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
