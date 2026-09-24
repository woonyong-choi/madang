package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.DriveFileMove
import androidx.compose.material.icons.automirrored.outlined.NoteAdd
import androidx.compose.material.icons.automirrored.outlined.Sort
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.PushPin
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material.icons.outlined.Tag
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.datetime.toLocalDateTime
import madang.api.model.BlockType
import madang.api.model.PageCard
import madang.api.model.PageStatus
import madang.api.model.ProjectSort
import madang.shared.main.ListSection
import madang.shared.main.ListSource
import madang.shared.main.MainState
import madang.shared.main.PageFilter
import madang.shared.main.Pane
import madang.shared.main.SectionHeader
import madang.shared.main.instantOrNull
import madang.shared.main.listSections
import madang.shared.main.sortOf

/** 2열 조작. */
class ListActions(
    val open: (PageCard) -> Unit,
    val newPage: () -> Unit,
    val setSort: (ProjectSort) -> Unit,
    val setFilter: (PageFilter) -> Unit,
    val setPinned: (PageCard, Boolean) -> Unit,
    val editTags: (PageCard) -> Unit,
    val move: (PageCard, String) -> Unit,
    val delete: (PageCard) -> Unit,
    val back: (() -> Unit)?
)

/** 2열: 머리(제목·새 페이지·정렬·필터), 날짜별로 묶은 카드, 아래에 "+ 페이지". */
@Composable
fun PageListColumn(state: MainState, actions: ListActions, modifier: Modifier) {
    val strings = LocalStrings.current.navigator
    val clock = LocalListClock.current
    val cards = state.listCards
    val sort = sortOf(state.source, state.projects)
    val sections = listSections(cards, sort, clock.now(), clock.zone)
    val listState = rememberLazyListState()
    val selectedIndex = lazyIndexOf(sections, state.selectedPage)
    LaunchedEffect(selectedIndex) {
        if (selectedIndex >= 0) {
            val visible = listState.layoutInfo.visibleItemsInfo.map { it.index }
            if (selectedIndex !in visible) listState.scrollToItem(selectedIndex)
        }
    }
    Column(modifier = modifier) {
        ListHeader(state, sort, actions)
        if (state.filter.isActive) FilterBar(state.filter, actions.setFilter)
        HorizontalDivider()
        Box(modifier = Modifier.weight(1f)) {
            if (cards.isEmpty()) {
                Text(
                    strings.noPages,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.align(Alignment.Center)
                )
            }
            LazyColumn(state = listState, modifier = Modifier.fillMaxSize()) {
                for (section in sections) {
                    sectionHeaderText(section.header, strings)?.let { title ->
                        item(key = "header:${section.header}") { SectionTitle(title) }
                    }
                    items(section.cards, key = { "card:${it.id}" }) { card ->
                        PageCardItem(
                            card = card,
                            state = state,
                            selected = card.id == state.selectedPage,
                            paneFocused = state.pane == Pane.LIST,
                            actions = actions
                        )
                        HorizontalDivider(
                            modifier = Modifier.padding(horizontal = 12.dp),
                            color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f)
                        )
                    }
                }
            }
        }
        HorizontalDivider()
        TextButton(onClick = actions.newPage, modifier = Modifier.padding(4.dp)) {
            Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(4.dp))
            Text(strings.newPage)
        }
    }
}

@Composable
private fun ListHeader(state: MainState, sort: ProjectSort, actions: ListActions) {
    val strings = LocalStrings.current.navigator
    val title = when (val source = state.source) {
        is ListSource.InProject -> state.projects.firstOrNull { it.id == source.id }?.title
            ?: source.id

        is ListSource.WithTag -> "#${source.path}"

        null -> ""
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 8.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        actions.back?.let { ToolbarIcon(Icons.AutoMirrored.Outlined.ArrowBack, strings.back, it) }
        Text(
            title,
            style = MaterialTheme.typography.titleSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(start = 4.dp).weight(1f)
        )
        Text(
            "${state.listCards.size}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(end = 4.dp)
        )
        ToolbarIcon(Icons.AutoMirrored.Outlined.NoteAdd, strings.newPage, actions.newPage)
        if (state.source is ListSource.InProject) SortMenu(sort, actions.setSort)
        FilterMenu(state, actions.setFilter)
    }
}

@Composable
private fun SortMenu(sort: ProjectSort, onSort: (ProjectSort) -> Unit) {
    val strings = LocalStrings.current.navigator
    var open by remember { mutableStateOf(false) }
    Box {
        ToolbarIcon(Icons.AutoMirrored.Outlined.Sort, strings.sort, { open = true })
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (option in SORTS) {
                CheckItem(strings.sortName(option), option == sort) {
                    open = false
                    onSort(option)
                }
            }
        }
    }
}

@Composable
private fun FilterMenu(state: MainState, onFilter: (PageFilter) -> Unit) {
    val strings = LocalStrings.current.navigator
    val filter = state.filter
    var open by remember { mutableStateOf(false) }
    Box {
        ToolbarIcon(
            Icons.Outlined.FilterList,
            strings.filter,
            { open = true },
            tint = if (filter.isActive) MaterialTheme.colorScheme.primary else null
        )
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (status in PageStatus.entries) {
                CheckItem(strings.status(status), status in filter.statuses) {
                    onFilter(filter.copy(statuses = filter.statuses.toggle(status)))
                }
            }
            HorizontalDivider()
            for (row in state.tagRows.filter { it.depth == 0 }) {
                CheckItem("#${row.path}", row.path in filter.tags) {
                    onFilter(filter.copy(tags = filter.tags.toggle(row.path)))
                }
            }
            if (filter.isActive) {
                HorizontalDivider()
                DropdownMenuItem(
                    text = { Text(strings.clearFilter) },
                    onClick = {
                        open = false
                        onFilter(PageFilter())
                    }
                )
            }
        }
    }
}

@Composable
private fun CheckItem(label: String, checked: Boolean, onClick: () -> Unit) {
    DropdownMenuItem(
        text = { Text(label) },
        onClick = onClick,
        leadingIcon = {
            Icon(
                Icons.Outlined.Check,
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = if (checked) MaterialTheme.colorScheme.primary else Color.Transparent
            )
        }
    )
}

@Composable
private fun FilterBar(filter: PageFilter, onFilter: (PageFilter) -> Unit) {
    val strings = LocalStrings.current.navigator
    val labels = filter.statuses.map(strings.status) + filter.tags.map { "#$it" }
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            labels.joinToString(" · "),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        TextButton(onClick = { onFilter(PageFilter()) }) {
            Text(strings.clearFilter, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(
        title,
        style = MaterialTheme.typography.labelMedium,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.fillMaxWidth().padding(start = 16.dp, top = 12.dp, bottom = 4.dp)
    )
}

@Composable
private fun PageCardItem(
    card: PageCard,
    state: MainState,
    selected: Boolean,
    paneFocused: Boolean,
    actions: ListActions
) {
    val strings = LocalStrings.current.navigator
    val colors = MaterialTheme.colorScheme
    val hover = remember { MutableInteractionSource() }
    val hovered by hover.collectIsHoveredAsState()
    val background = when {
        selected && paneFocused -> colors.primaryContainer
        selected -> colors.surfaceVariant
        else -> Color.Transparent
    }
    ContextMenuBox(actions = { cardMenu(card, state, actions, strings) }) { menu ->
        Box(
            modifier = menu
                .fillMaxWidth()
                .padding(horizontal = 6.dp, vertical = 2.dp)
                .background(background, RoundedCornerShape(8.dp))
                .hoverable(hover)
                .dragSource(card)
                .clickable { actions.open(card) }
        ) {
            CardBody(card, state)
            if (hovered) {
                QuickActions(card, state, actions, Modifier.align(Alignment.TopEnd))
            }
        }
    }
}

@Composable
private fun CardBody(card: PageCard, state: MainState) {
    val strings = LocalStrings.current.navigator
    val colors = MaterialTheme.colorScheme
    val source = state.source
    Column(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (card.pinned) {
                Icon(
                    Icons.Filled.PushPin,
                    contentDescription = null,
                    modifier = Modifier.padding(end = 4.dp).size(12.dp),
                    tint = colors.onSurfaceVariant
                )
            }
            Text(
                card.title,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f)
            )
            StatusChip(card.status, Modifier.padding(start = 6.dp))
        }
        Row {
            Text(
                cardTime(card, sortOf(state.source, state.projects)),
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(end = 6.dp)
            )
            Text(
                card.preview.orEmpty(),
                style = MaterialTheme.typography.bodySmall,
                color = colors.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        val counts = blockCountsText(card.blockCounts, strings)
        val run = card.lastRun?.let { "${it.runner}/${it.model}" }
        if (counts.isNotEmpty() || run != null) {
            Row {
                Text(
                    counts,
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                run?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = colors.primary)
                }
            }
        }
        val fromOtherProject = source is ListSource.InProject && source.id != card.project
        if (fromOtherProject || card.tags.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (fromOtherProject) {
                    Icon(
                        Icons.Outlined.Folder,
                        contentDescription = null,
                        modifier = Modifier.padding(end = 3.dp).size(12.dp),
                        tint = colors.onSurfaceVariant
                    )
                    Text(
                        state.projects.firstOrNull { it.id == card.project }?.title ?: card.project,
                        style = MaterialTheme.typography.labelSmall,
                        color = colors.onSurfaceVariant,
                        modifier = Modifier.padding(end = 8.dp)
                    )
                }
                Text(
                    card.tags.joinToString(" ") { "#$it" },
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.tertiary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}

@Composable
private fun QuickActions(
    card: PageCard,
    state: MainState,
    actions: ListActions,
    modifier: Modifier
) {
    val strings = LocalStrings.current.navigator
    var moving by remember { mutableStateOf(false) }
    Surface(
        modifier = modifier.padding(4.dp),
        shape = RoundedCornerShape(6.dp),
        tonalElevation = 3.dp,
        shadowElevation = 2.dp
    ) {
        Row {
            QuickIcon(
                if (card.pinned) Icons.Filled.PushPin else Icons.Outlined.PushPin,
                if (card.pinned) strings.unpin else strings.pin
            ) { actions.setPinned(card, !card.pinned) }
            QuickIcon(Icons.Outlined.Tag, strings.tag) { actions.editTags(card) }
            Box {
                QuickIcon(Icons.AutoMirrored.Outlined.DriveFileMove, strings.move) { moving = true }
                DropdownMenu(expanded = moving, onDismissRequest = { moving = false }) {
                    for (project in state.projects.filter { it.id != card.project }) {
                        DropdownMenuItem(
                            text = { Text(project.title) },
                            onClick = {
                                moving = false
                                actions.move(card, project.id)
                            }
                        )
                    }
                }
            }
            QuickIcon(Icons.Outlined.DeleteOutline, strings.delete) { actions.delete(card) }
        }
    }
}

@Composable
private fun QuickIcon(icon: ImageVector, label: String, onClick: () -> Unit) {
    ToolbarIcon(icon, label, onClick)
}

private fun cardMenu(
    card: PageCard,
    state: MainState,
    actions: ListActions,
    strings: NavigatorStrings
): List<MenuAction> = listOf(
    MenuAction(if (card.pinned) strings.unpin else strings.pin) {
        actions.setPinned(card, !card.pinned)
    },
    MenuAction(strings.tag) { actions.editTags(card) }
) + state.projects.filter { it.id != card.project }.map { project ->
    MenuAction("${strings.move}: ${project.title}") { actions.move(card, project.id) }
} + MenuAction(strings.delete) { actions.delete(card) }

/** 카드 시각. 생성순이면 생성 시각, 아니면 갱신 시각(목록 묶음과 같은 기준). */
@Composable
private fun cardTime(card: PageCard, sort: ProjectSort): String {
    val clock = LocalListClock.current
    val strings = LocalStrings.current.navigator
    val stamp = if (sort == ProjectSort.CREATED) card.created else card.updated
    val instant = instantOrNull(stamp) ?: return ""
    val time = instant.toLocalDateTime(clock.zone)
    val today = clock.now().toLocalDateTime(clock.zone).date
    return strings.cardTime(time, time.date == today, time.year == today.year)
}

/** 블록 종류별 개수 한 줄. 메시지·실행 다음에 나머지를 계약의 종류 순서로. */
fun blockCountsText(counts: Map<String, Int>, strings: NavigatorStrings): String =
    BlockType.entries.mapNotNull { type ->
        counts[type.value]?.takeIf { it > 0 }?.let { "${strings.blockType(type)} $it" }
    }.joinToString(" · ")

private fun sectionHeaderText(header: SectionHeader, strings: NavigatorStrings): String? =
    when (header) {
        SectionHeader.Pinned -> strings.pinnedSection
        SectionHeader.Today -> strings.today
        SectionHeader.Yesterday -> strings.yesterday
        SectionHeader.Previous7Days -> strings.previous7Days
        SectionHeader.Previous30Days -> strings.previous30Days
        is SectionHeader.Month -> strings.month(header.year, header.month)
        is SectionHeader.Year -> strings.year(header.year)
        SectionHeader.Plain -> null
    }

/** 묶음 머리를 포함한 LazyColumn 안에서 [pageId] 카드의 위치. 카드마다 구분선 항목은 없다. */
private fun lazyIndexOf(sections: List<ListSection>, pageId: String?): Int {
    if (pageId == null) return -1
    var index = 0
    for (section in sections) {
        if (section.header != SectionHeader.Plain) index++
        val at = section.cards.indexOfFirst { it.id == pageId }
        if (at >= 0) return index + at
        index += section.cards.size
    }
    return -1
}

private fun <T> Set<T>.toggle(item: T): Set<T> = if (item in this) this - item else this + item
