package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import madang.shared.main.EventLink
import madang.shared.main.MainState
import madang.shared.main.MainViewModel

/** 메인 화면. 3열(탐색 / 목록 / 본문) 자리표시와 연결 상태 줄. */
@Composable
fun MainScreen(viewModel: MainViewModel, onOpenSettings: () -> Unit) {
    val state by viewModel.state.collectAsState()
    Column(modifier = Modifier.fillMaxSize()) {
        StatusBar(state, onOpenSettings)
        HorizontalDivider()
        Row(modifier = Modifier.fillMaxSize()) {
            SpacesPane(state, Modifier.width(240.dp).fillMaxHeight())
            VerticalDivider()
            EventsPane(state, Modifier.width(320.dp).fillMaxHeight())
            VerticalDivider()
            Column(
                modifier = Modifier.weight(1f).fillMaxHeight(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("Content", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun StatusBar(state: MainState, onOpenSettings: () -> Unit) {
    val strings = LocalStrings.current
    val link = when (val current = state.link) {
        EventLink.Connecting -> strings.eventsConnecting
        EventLink.Live -> strings.eventsLive
        is EventLink.Retrying -> "${strings.eventsRetrying} (${current.retryIn})"
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("core ${state.baseUrl}", style = MaterialTheme.typography.bodySmall)
        Text(link, style = MaterialTheme.typography.bodySmall)
        Text(
            state.loadError.orEmpty(),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.weight(1f)
        )
        TextButton(onClick = onOpenSettings) { Text(strings.settings) }
    }
}

@Composable
private fun SpacesPane(state: MainState, modifier: Modifier) {
    Column(modifier = modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(LocalStrings.current.spaces, style = MaterialTheme.typography.titleSmall)
        for (space in state.spaces) {
            Text("${space.title} (${space.pages ?: 0})")
        }
    }
}

@Composable
private fun EventsPane(state: MainState, modifier: Modifier) {
    val strings = LocalStrings.current
    Column(modifier = modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(strings.recentEvents, style = MaterialTheme.typography.titleSmall)
        if (state.recentEvents.isEmpty()) {
            Text(strings.noEvents, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        for (event in state.recentEvents) {
            Text(
                listOfNotNull(event.type, event.page).joinToString("  "),
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}
