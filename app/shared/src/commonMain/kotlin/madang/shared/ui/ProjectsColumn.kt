package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.CreateNewFolder
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Tag
import androidx.compose.material.icons.outlined.UnfoldLess
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TooltipAnchorPosition
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.rememberTooltipState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.PageStatus
import madang.shared.main.ListSource
import madang.shared.main.MainState
import madang.shared.main.Pane
import madang.shared.main.ProjectRow
import madang.shared.main.TagRow
import madang.shared.main.projectStats

/** 1열 조작. 화면이 ViewModel과 대화상자로 이어 준다. */
class ProjectsActions(
    val select: (ListSource) -> Unit,
    val toggleProject: (String) -> Unit,
    val toggleTag: (String) -> Unit,
    val collapseAll: () -> Unit,
    val focusOn: (String?) -> Unit,
    val addProject: () -> Unit,
    val rename: (ProjectRow) -> Unit,
    val remove: (ProjectRow) -> Unit,
    val openTrash: () -> Unit,
    val openSettings: () -> Unit
)

/**
 * 1열: 프로젝트 트리와 태그 트리, 아래에 "+ 프로젝트". 프로젝트 줄은 이름을 보이고 마우스를
 * 올리면 폴더 경로를 보인다. "+ 프로젝트"는 폴더를 골라 등록한다.
 */
@Composable
fun ProjectsColumn(state: MainState, actions: ProjectsActions, modifier: Modifier) {
    val strings = LocalStrings.current
    val focused = state.pane == Pane.PROJECTS
    val stats = projectStats(state.cards)
    Column(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                strings.projects,
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.weight(1f)
            )
            ToolbarIcon(
                Icons.Outlined.UnfoldLess,
                strings.navigator.collapseAll,
                actions.collapseAll
            )
            ToolbarIcon(
                Icons.Outlined.CreateNewFolder,
                strings.navigator.newProject,
                actions.addProject
            )
            ToolbarIcon(Icons.Outlined.Settings, strings.settings, actions.openSettings)
        }
        state.focusProject?.let { id ->
            val title = state.projects.firstOrNull { it.id == id }?.title ?: id
            FocusBanner("${strings.navigator.focused}: $title") { actions.focusOn(null) }
        }
        LazyColumn(modifier = Modifier.weight(1f).padding(horizontal = 6.dp)) {
            if (state.loaded && state.projects.isEmpty()) {
                item(key = "no-projects") {
                    Text(
                        strings.navigator.noProjects,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(8.dp)
                    )
                }
            }
            items(state.projectRows, key = { "project:${it.project.id}" }) { row ->
                val stat = stats[row.project.id]
                ProjectRowItem(
                    row = row,
                    count = stat?.pages ?: row.project.pages ?: 0,
                    active = stat?.active ?: ((row.project.activePages ?: 0) > 0),
                    selected = state.source == ListSource.InProject(row.project.id),
                    paneFocused = focused,
                    focusedProject = state.focusProject == row.project.id,
                    actions = actions
                )
            }
            if (state.tagRows.isNotEmpty()) {
                item(key = "tags-header") {
                    Text(
                        strings.navigator.tags,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 8.dp, top = 16.dp, bottom = 4.dp)
                    )
                }
            }
            items(state.tagRows, key = { "tag:${it.path}" }) { row ->
                TagRowItem(
                    row = row,
                    selected = state.source == ListSource.WithTag(row.path),
                    paneFocused = focused,
                    actions = actions
                )
            }
        }
        HorizontalDivider()
        TextButton(onClick = actions.addProject, modifier = Modifier.padding(4.dp)) {
            Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(4.dp))
            Text(strings.navigator.newProject)
        }
    }
}

@Composable
private fun ProjectRowItem(
    row: ProjectRow,
    count: Int,
    active: Boolean,
    selected: Boolean,
    paneFocused: Boolean,
    focusedProject: Boolean,
    actions: ProjectsActions
) {
    val strings = LocalStrings.current.navigator
    val trashLabel = LocalStrings.current.page.recentlyDeleted
    val id = row.project.id
    ContextMenuBox(
        actions = {
            listOf(
                if (focusedProject) {
                    MenuAction(strings.unfocus) { actions.focusOn(null) }
                } else {
                    MenuAction(strings.focus) { actions.focusOn(id) }
                },
                MenuAction(strings.rename) { actions.rename(row) },
                MenuAction(trashLabel, actions.openTrash),
                MenuAction(strings.removeProject) { actions.remove(row) }
            )
        }
    ) { menu ->
        PathTooltip(row.project.path) {
            NavRow(
                depth = row.depth,
                expandable = row.hasChildren,
                expanded = row.expanded,
                onToggle = { actions.toggleProject(id) },
                icon = projectIcon(row.project.icon),
                iconTint = parseColor(row.project.color),
                label = row.project.title,
                count = count,
                active = active,
                selected = selected,
                paneFocused = paneFocused,
                target = DropTarget.ToProject(id),
                modifier = menu,
                onClick = { actions.select(ListSource.InProject(id)) }
            )
        }
    }
}

/** 마우스를 올리면 [path]를 보이는 툴팁. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PathTooltip(path: String, content: @Composable () -> Unit) {
    TooltipBox(
        positionProvider = TooltipDefaults.rememberTooltipPositionProvider(
            TooltipAnchorPosition.Below
        ),
        tooltip = { PlainTooltip { Text(path) } },
        state = rememberTooltipState(),
        content = content
    )
}

@Composable
private fun TagRowItem(
    row: TagRow,
    selected: Boolean,
    paneFocused: Boolean,
    actions: ProjectsActions
) {
    NavRow(
        depth = row.depth,
        expandable = row.hasChildren,
        expanded = row.expanded,
        onToggle = { actions.toggleTag(row.path) },
        icon = Icons.Outlined.Tag,
        iconTint = null,
        label = row.name,
        count = row.count,
        active = false,
        selected = selected,
        paneFocused = paneFocused,
        target = DropTarget.ToTag(row.path),
        modifier = Modifier,
        onClick = { actions.select(ListSource.WithTag(row.path)) }
    )
}

@Composable
private fun NavRow(
    depth: Int,
    expandable: Boolean,
    expanded: Boolean,
    onToggle: () -> Unit,
    icon: ImageVector,
    iconTint: Color?,
    label: String,
    count: Int,
    active: Boolean,
    selected: Boolean,
    paneFocused: Boolean,
    target: DropTarget,
    modifier: Modifier,
    onClick: () -> Unit
) {
    val colors = MaterialTheme.colorScheme
    val dropHover = LocalDragDrop.current?.hovered == target
    val background = when {
        dropHover -> colors.tertiaryContainer
        selected && paneFocused -> colors.primaryContainer
        selected -> colors.surfaceVariant
        else -> Color.Transparent
    }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(30.dp)
            .dropTarget(target)
            .background(background, RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(start = (4 + depth * 16).dp, end = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier.size(18.dp).then(
                if (expandable) Modifier.clickable(onClick = onToggle) else Modifier
            ),
            contentAlignment = Alignment.Center
        ) {
            if (expandable) {
                Icon(
                    if (expanded) Icons.Outlined.ExpandMore else Icons.Outlined.ChevronRight,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = colors.onSurfaceVariant
                )
            }
        }
        Icon(
            icon,
            contentDescription = null,
            modifier = Modifier.padding(start = 2.dp, end = 6.dp).size(16.dp),
            tint = iconTint ?: colors.onSurfaceVariant
        )
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        if (active) {
            Box(
                Modifier.padding(horizontal = 6.dp).size(7.dp)
                    .background(statusColor(PageStatus.DOING), CircleShape)
            )
        }
        if (count > 0) {
            Text(
                "$count",
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun FocusBanner(label: String, onClear: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp)
            .background(MaterialTheme.colorScheme.secondaryContainer, RoundedCornerShape(6.dp))
            .padding(start = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label, style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
        IconButton(onClick = onClear, modifier = Modifier.size(28.dp)) {
            Icon(Icons.Outlined.Close, contentDescription = null, modifier = Modifier.size(14.dp))
        }
    }
}

/** 열 머리의 작은 아이콘 버튼. */
@Composable
fun ToolbarIcon(icon: ImageVector, label: String, onClick: () -> Unit, tint: Color? = null) {
    IconButton(onClick = onClick, modifier = Modifier.size(32.dp)) {
        Icon(
            icon,
            contentDescription = label,
            modifier = Modifier.size(18.dp),
            tint = tint ?: MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
