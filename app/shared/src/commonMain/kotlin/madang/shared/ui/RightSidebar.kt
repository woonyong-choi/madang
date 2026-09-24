package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import madang.shared.main.MemoryState
import madang.shared.main.SideTab
import madang.shared.main.Sidebar

/** 오른쪽 사이드바 조작. */
class SidebarActions(
    val select: (SideTab) -> Unit,
    val close: () -> Unit,
    val memory: MemoryActions
)

/**
 * 가운데 열 오른쪽의 탭 사이드바: 지금 · 파일 · 메모리 · git · 포트 · 기록.
 *
 * 지금은 메모리 탭만 내용이 있고, 나머지 탭은 자리만 있다.
 */
@Composable
fun RightSidebar(
    sidebar: Sidebar,
    memory: MemoryState,
    actions: SidebarActions,
    modifier: Modifier
) {
    Column(modifier = modifier.background(MaterialTheme.colorScheme.surfaceContainerLow)) {
        SideTabRow(sidebar.tab, actions)
        HorizontalDivider()
        val content = Modifier.weight(1f).fillMaxWidth()
        when (sidebar.tab) {
            SideTab.MEMORY -> MemoryTab(memory, actions.memory, content)
            else -> EmptySideTab(content)
        }
    }
}

@Composable
private fun SideTabRow(selected: SideTab, actions: SidebarActions) {
    val strings = LocalStrings.current.page
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, top = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(modifier = Modifier.weight(1f)) {
            SideTab.entries.forEach { tab ->
                val active = tab == selected
                TextButton(
                    onClick = { actions.select(tab) },
                    contentPadding = PaddingValues(horizontal = 8.dp)
                ) {
                    Text(
                        strings.sideTab(tab),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
                        color = if (active) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        }
                    )
                }
            }
        }
        ToolbarIcon(Icons.Outlined.Close, strings.close, actions.close)
    }
}

@Composable
private fun EmptySideTab(modifier: Modifier) {
    Column(modifier = modifier) {
        Text(
            LocalStrings.current.page.sideTabPending,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(12.dp)
        )
    }
}
