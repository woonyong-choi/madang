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
import madang.shared.main.FilesState
import madang.shared.main.GitState
import madang.shared.main.MainState
import madang.shared.main.MemoryState
import madang.shared.main.NowState
import madang.shared.main.PortsState
import madang.shared.main.SideTab

/** 오른쪽 사이드바 조작. [openRun]은 열린 페이지의 run 탭을 연다(기록 탭). */
class SidebarActions(
    val select: (SideTab) -> Unit,
    val close: () -> Unit,
    val memory: MemoryActions,
    val now: NowActions,
    val files: FilesActions,
    val git: GitActions,
    val ports: PortsActions,
    val openRun: (Int) -> Unit
)

/** 사이드바 탭들이 따로 받아 둔 상태. */
class SidebarStates(
    val memory: MemoryState,
    val now: NowState,
    val files: FilesState,
    val git: GitState,
    val ports: PortsState
)

/**
 * 가운데 열 오른쪽의 탭 사이드바: 지금 · 파일 · 메모리 · git · 포트 · 기록.
 *
 * 지금 탭은 모든 프로젝트를, 나머지 탭은 열린 페이지(없으면 고른 프로젝트)를 따른다.
 */
@Composable
fun RightSidebar(
    state: MainState,
    tabs: SidebarStates,
    actions: SidebarActions,
    modifier: Modifier
) {
    Column(modifier = modifier.background(MaterialTheme.colorScheme.surfaceContainerLow)) {
        SideTabRow(state.sidebar.tab, actions)
        HorizontalDivider()
        val content = Modifier.weight(1f).fillMaxWidth()
        when (state.sidebar.tab) {
            SideTab.NOW -> NowTab(state, tabs.now, actions.now, content)
            SideTab.FILES -> FilesTab(tabs.files, actions.files, content)
            SideTab.MEMORY -> MemoryTab(tabs.memory, actions.memory, content)
            SideTab.GIT -> GitTab(tabs.git, actions.git, state::pageTitle, content)
            SideTab.PORTS -> PortsTab(tabs.ports, actions.ports, content)
            SideTab.HISTORY -> HistoryTab(state.page?.detail, actions.openRun, content)
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
