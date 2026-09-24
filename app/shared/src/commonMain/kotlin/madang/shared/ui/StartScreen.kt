package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import madang.shared.core.LocateStep
import madang.shared.start.StartState
import madang.shared.start.StartViewModel

@Composable
fun StartScreen(viewModel: StartViewModel) {
    val state by viewModel.state.collectAsState()
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        when (val current = state) {
            is StartState.Locating -> Locating(current.step)
            is StartState.Failed -> Failed(current, viewModel::retry)
            is StartState.Connected -> CircularProgressIndicator()
        }
    }
}

@Composable
private fun Locating(step: LocateStep?) {
    val strings = LocalStrings.current
    CircularProgressIndicator()
    Text(strings.locating, style = MaterialTheme.typography.titleMedium)
    val detail = when (step) {
        is LocateStep.Probing -> "${strings.probing}: ${step.baseUrl}"
        LocateStep.Launching -> strings.launching
        LocateStep.WaitingForStart -> strings.waitingForStart
        null -> ""
    }
    Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun Failed(state: StartState.Failed, onRetry: () -> Unit) {
    val strings = LocalStrings.current
    Column(
        modifier = Modifier.widthIn(max = 560.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(strings.connectFailed, style = MaterialTheme.typography.headlineSmall)
        Text(strings.failureReason(state.reason))
        state.detail?.let {
            Text(
                it,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error
            )
        }
        Text(
            "${strings.triedAddresses}: ${state.tried.joinToString()}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            strings.openSettingsHint,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Button(onClick = onRetry) { Text(strings.retry) }
    }
}
