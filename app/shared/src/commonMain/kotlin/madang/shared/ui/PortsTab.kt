package madang.shared.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
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
import madang.api.model.ObservedPort
import madang.shared.main.Load
import madang.shared.main.PortsState

/** 포트 탭 조작. [openUrl]은 URL을 브라우저 탭으로 연다. */
class PortsActions(
    val reload: () -> Unit,
    val toggleDeclare: (Int) -> Unit,
    val setName: (Int, String) -> Unit,
    val declare: (Int) -> Unit,
    val openUrl: (String) -> Unit,
    val onEditing: (Boolean) -> Unit
)

/**
 * 사이드바 포트 탭: core가 관찰한 열린 포트. 선언된 실행 대상이 연 포트는 그 이름을, 아니면
 * "선언으로 저장"을 보인다. 두 번 누르면 `http://localhost:<포트>`를 브라우저 탭으로 연다.
 */
@Composable
fun PortsTab(state: PortsState, actions: PortsActions, modifier: Modifier) {
    val strings = LocalStrings.current.side
    Column(modifier = modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Row(modifier = Modifier.weight(1f)) { state.error?.let { SideError(it) } }
            ToolbarIcon(Icons.Outlined.Refresh, strings.reload, actions.reload)
        }
        when (val ports = state.ports) {
            null -> SideNote(strings.noProject)

            Load.Loading -> SideNote(strings.loading)

            is Load.Failed -> SideError(strings.failed(ports.message))

            is Load.Ready -> {
                if (ports.value.isEmpty()) SideNote(strings.portsEmpty)
                ports.value.forEach { port ->
                    PortRow(port, state.names[port.port], actions)
                    HorizontalDivider()
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun PortRow(port: ObservedPort, name: String?, actions: PortsActions) {
    val strings = LocalStrings.current.side
    val colors = MaterialTheme.colorScheme
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .combinedClickable(
                onClick = {},
                onDoubleClick = { actions.openUrl("http://localhost:${port.port}") }
            )
            .padding(vertical = 6.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                ":${port.port}",
                style = MaterialTheme.typography.bodyMedium,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.SemiBold
            )
            Text(
                "${port.host} · pid ${port.pid}",
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant,
                modifier = Modifier.padding(start = 8.dp).weight(1f)
            )
            val declared = port.run
            if (declared != null) {
                Text(
                    strings.portDeclared(declared),
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.primary
                )
            } else {
                TextButton(
                    onClick = { actions.toggleDeclare(port.port) },
                    contentPadding = PaddingValues(horizontal = 6.dp)
                ) {
                    Text(
                        if (name != null) strings.cancel else strings.portDeclare,
                        style = MaterialTheme.typography.labelSmall
                    )
                }
            }
        }
        listOfNotNull(port.command, port.cwd).forEach {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                color = colors.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        if (name != null) DeclareField(port.port, name, actions)
    }
}

@Composable
private fun DeclareField(port: Int, name: String, actions: PortsActions) {
    val strings = LocalStrings.current.side
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
        OutlinedTextField(
            value = name,
            onValueChange = { actions.setName(port, it) },
            placeholder = { Text(strings.portNamePlaceholder) },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodySmall,
            modifier = Modifier.weight(1f).onFocusChanged { actions.onEditing(it.isFocused) }
        )
        TextButton(onClick = { actions.declare(port) }, enabled = name.isNotBlank()) {
            Text(strings.save)
        }
    }
}
