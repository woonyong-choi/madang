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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import madang.shared.main.ROOT_SPACE
import madang.shared.main.SpaceRow
import madang.shared.main.TagRow
import madang.shared.main.spaceStats

/** 1열 조작. 화면이 ViewModel과 대화상자로 이어 준다. */
class SpacesActions(
    val select: (ListSource) -> Unit,
    val toggleSpace: (String) -> Unit,
    val toggleTag: (String) -> Unit,
    val collapseAll: () -> Unit,
    val focusOn: (String?) -> Unit,
    val newSpace: () -> Unit,
    val rename: (SpaceRow) -> Unit,
    val linkRepo: (SpaceRow) -> Unit,
    val delete: (SpaceRow) -> Unit,
    val openTrash: () -> Unit,
    val openSettings: () -> Unit
)

/** 1열: 공간 트리와 태그 트리, 아래에 "+ 공간". */
@Composable
fun SpacesColumn(state: MainState, actions: SpacesActions, modifier: Modifier) {
    val strings = LocalStrings.current
    val focused = state.pane == Pane.SPACES
    val stats = spaceStats(state.cards)
    Column(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                strings.spaces,
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
                strings.navigator.newSpace,
                actions.newSpace
            )
            ToolbarIcon(Icons.Outlined.Settings, strings.settings, actions.openSettings)
        }
        state.focusSpace?.let { slug ->
            val title = state.spaces.firstOrNull { it.slug == slug }?.title ?: slug
            FocusBanner("${strings.navigator.focused}: $title") { actions.focusOn(null) }
        }
        LazyColumn(modifier = Modifier.weight(1f).padding(horizontal = 6.dp)) {
            items(state.spaceRows, key = { "space:${it.space.slug}" }) { row ->
                val stat = stats[row.space.slug]
                SpaceRowItem(
                    row = row,
                    count = stat?.pages ?: row.space.pages ?: 0,
                    active = stat?.active ?: ((row.space.activePages ?: 0) > 0),
                    selected = state.source == ListSource.InSpace(row.space.slug),
                    paneFocused = focused,
                    focusedSpace = state.focusSpace == row.space.slug,
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
        TextButton(onClick = actions.newSpace, modifier = Modifier.padding(4.dp)) {
            Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(4.dp))
            Text(strings.navigator.newSpace)
        }
    }
}

@Composable
private fun SpaceRowItem(
    row: SpaceRow,
    count: Int,
    active: Boolean,
    selected: Boolean,
    paneFocused: Boolean,
    focusedSpace: Boolean,
    actions: SpacesActions
) {
    val strings = LocalStrings.current.navigator
    val trashLabel = LocalStrings.current.page.recentlyDeleted
    val slug = row.space.slug
    ContextMenuBox(
        actions = {
            listOf(
                if (focusedSpace) {
                    MenuAction(strings.unfocus) { actions.focusOn(null) }
                } else {
                    MenuAction(strings.focus) { actions.focusOn(slug) }
                },
                MenuAction(strings.rename) { actions.rename(row) },
                MenuAction(strings.linkRepo) { actions.linkRepo(row) },
                MenuAction(trashLabel, actions.openTrash)
            ) +
                if (slug !=
                    ROOT_SPACE
                ) {
                    listOf(MenuAction(strings.delete) { actions.delete(row) })
                } else {
                    emptyList()
                }
        }
    ) { menu ->
        NavRow(
            depth = row.depth,
            expandable = row.hasChildren,
            expanded = row.expanded,
            onToggle = { actions.toggleSpace(slug) },
            icon = spaceIcon(row.space.icon, slug == ROOT_SPACE),
            iconTint = parseColor(row.space.color),
            label = row.space.title,
            count = count,
            active = active,
            selected = selected,
            paneFocused = paneFocused,
            target = DropTarget.ToSpace(slug),
            modifier = menu,
            onClick = { actions.select(ListSource.InSpace(slug)) }
        )
    }
}

@Composable
private fun TagRowItem(
    row: TagRow,
    selected: Boolean,
    paneFocused: Boolean,
    actions: SpacesActions
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
