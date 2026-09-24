package madang.shared.ui

import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
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
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEvent
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isAltPressed
import androidx.compose.ui.input.key.isCtrlPressed
import androidx.compose.ui.input.key.isMetaPressed
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.unit.dp
import madang.shared.main.EventLink
import madang.shared.main.MainState
import madang.shared.main.MainViewModel
import madang.shared.main.NavKey
import madang.shared.main.Pane
import madang.shared.main.visiblePanes

/**
 * 메인 화면: 레이어 0의 3열(공간 / 페이지 목록 / 페이지 본문)과 아래 상태 줄.
 *
 * 입력창이나 메모리 편집기에 포커스가 있으면 글자·화살표 키는 그쪽이 받고, Cmd/Ctrl 단축키와
 * Esc만 화면이 받는다.
 */
@Composable
fun MainScreen(viewModel: MainViewModel, onOpenSettings: () -> Unit) {
    val state by viewModel.state.collectAsState()
    val composer by viewModel.composer.state.collectAsState()
    val memory by viewModel.memory.state.collectAsState()
    val strings = LocalStrings.current.navigator
    val focus = remember { FocusRequester() }
    var dialog by remember { mutableStateOf<MainDialog?>(null) }
    var editing by remember { mutableStateOf(false) }
    var origin by remember { mutableStateOf(Offset.Zero) }
    val drag = remember(viewModel) {
        DragDropState { card, target ->
            when (target) {
                is DropTarget.ToSpace -> viewModel.movePage(card.id, target.slug)
                is DropTarget.ToTag -> viewModel.addTag(card.id, target.path)
            }
        }
    }
    LaunchedEffect(dialog) { if (dialog == null) focus.requestFocus() }

    CompositionLocalProvider(LocalDragDrop provides drag) {
        BoxWithConstraints(
            modifier = Modifier
                .fillMaxSize()
                .onGloballyPositioned { origin = it.positionInWindow() }
                .focusRequester(focus)
                .focusable()
                .onPreviewKeyEvent { event ->
                    when (val shortcut = shortcut(event, editing, memory.isOpen)) {
                        null -> false

                        Shortcut.Search -> true.also { dialog = MainDialog.Search }

                        Shortcut.Memory -> true.also { viewModel.toggleMemory() }

                        Shortcut.CloseMemory -> true.also {
                            viewModel.memory.close()
                            focus.requestFocus()
                        }

                        is Shortcut.Nav -> true.also {
                            if (editing) focus.requestFocus()
                            viewModel.onKey(shortcut.key)
                        }
                    }
                }
        ) {
            val panes = visiblePanes(maxWidth.value, state.pane)
            Column(modifier = Modifier.fillMaxSize()) {
                Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
                    panes.forEachIndexed { index, pane ->
                        if (index > 0) VerticalDivider()
                        val width = paneModifier(pane, panes.size)
                        when (pane) {
                            Pane.SPACES -> SpacesColumn(
                                state,
                                spacesActions(viewModel, state, panes, onOpenSettings) {
                                    dialog = it
                                },
                                width
                            )

                            Pane.LIST -> PageListColumn(
                                state,
                                listActions(viewModel, panes) { dialog = it },
                                width
                            )

                            Pane.PAGE -> PageColumn(
                                state,
                                composer,
                                memory,
                                pageActions(
                                    viewModel,
                                    panes,
                                    onEditing = { editing = it },
                                    onEscape = { focus.requestFocus() }
                                ),
                                width
                            )
                        }
                    }
                }
                HorizontalDivider()
                StatusLine(state)
            }
            DragGhost(drag, origin) { target ->
                when (target) {
                    is DropTarget.ToSpace -> strings.dropToMove(
                        state.spaces.firstOrNull { it.slug == target.slug }?.title ?: target.slug
                    )

                    is DropTarget.ToTag -> strings.dropToTag(target.path)
                }
            }
        }
    }
    dialog?.let { MainDialogView(it, viewModel) { dialog = null } }
    val unknownFiles = state.page?.detail?.unknownFiles.orEmpty()
    if (state.unknownFilesOpen && unknownFiles.isNotEmpty()) {
        UnknownFilesDialog(unknownFiles, viewModel::resolveUnknownFile) {
            viewModel.showUnknownFiles(false)
        }
    }
}

private fun paneModifier(pane: Pane, count: Int): Modifier = when {
    count == 1 -> Modifier.fillMaxSize()
    pane == Pane.SPACES && count == 3 -> Modifier.width(240.dp).fillMaxHeight()
    pane == Pane.PAGE -> Modifier.fillMaxHeight().fillMaxWidth()
    else -> Modifier.width(340.dp).fillMaxHeight()
}

private fun spacesActions(
    viewModel: MainViewModel,
    state: MainState,
    panes: List<Pane>,
    onOpenSettings: () -> Unit,
    show: (MainDialog) -> Unit
) = SpacesActions(
    select = { viewModel.select(it, advance = Pane.LIST !in panes) },
    toggleSpace = viewModel::toggleSpace,
    toggleTag = viewModel::toggleTag,
    collapseAll = { state.expandedSpaces.forEach(viewModel::toggleSpace) },
    focusOn = viewModel::focusOn,
    newSpace = { show(MainDialog.NewSpace) },
    rename = { show(MainDialog.RenameSpace(it.space.slug, it.space.title)) },
    linkRepo = { show(MainDialog.LinkRepo(it.space.slug, it.space.repo.orEmpty())) },
    delete = { show(MainDialog.DeleteSpace(it.space.slug, it.space.title)) },
    openTrash = { show(MainDialog.Trash) },
    openSettings = onOpenSettings
)

private fun pageActions(
    viewModel: MainViewModel,
    panes: List<Pane>,
    onEditing: (Boolean) -> Unit,
    onEscape: () -> Unit
) = PageActions(
    toggleExpandAll = viewModel::toggleExpandAll,
    toggleFold = viewModel::toggleFold,
    cancelRun = viewModel::cancelRun,
    back = { viewModel.focusPane(Pane.LIST) }.takeIf { Pane.LIST !in panes },
    toggleMemory = viewModel::toggleMemory,
    showUnknownFiles = { viewModel.showUnknownFiles(true) },
    answer = viewModel::answer,
    composer = ComposerActions(
        setText = viewModel.composer::setText,
        complete = viewModel.composer::complete,
        send = viewModel::send,
        onEditing = onEditing,
        onEscape = onEscape
    ),
    memory = MemoryActions(
        select = viewModel.memory::select,
        edit = viewModel.memory::edit,
        save = viewModel.memory::save,
        close = viewModel.memory::close,
        onEditing = onEditing
    )
)

private fun listActions(viewModel: MainViewModel, panes: List<Pane>, show: (MainDialog) -> Unit) =
    ListActions(
        open = { viewModel.openPage(it.id, advance = Pane.PAGE !in panes) },
        newPage = viewModel::newPage,
        setSort = viewModel::setSort,
        setFilter = viewModel::setFilter,
        setPinned = { card, pinned -> viewModel.setPinned(card.id, pinned) },
        editTags = { show(MainDialog.EditTags(it.id, it.tags)) },
        move = { card, space -> viewModel.movePage(card.id, space) },
        delete = { show(MainDialog.DeletePage(it.id, it.title)) },
        back = { viewModel.focusPane(Pane.SPACES) }.takeIf { Pane.SPACES !in panes }
    )

/** 메인 화면이 가로채는 키. */
private sealed interface Shortcut {
    data object Search : Shortcut

    data object Memory : Shortcut

    data object CloseMemory : Shortcut

    data class Nav(val key: NavKey) : Shortcut
}

/**
 * 키 입력을 메인 화면 동작으로. [editing]이면 Cmd/Ctrl 단축키와 Esc만 받는다. 화면이 받지 않는
 * 키는 null.
 */
private fun shortcut(event: KeyEvent, editing: Boolean, memoryOpen: Boolean): Shortcut? {
    if (event.type != KeyEventType.KeyDown) return null
    val command = event.isMetaPressed || event.isCtrlPressed
    val plain = !command && !event.isAltPressed && !event.isShiftPressed
    return when {
        command && event.key == Key.K -> Shortcut.Search
        event.key == Key.Escape && memoryOpen -> Shortcut.CloseMemory
        editing && !command -> null
        plain && event.key == Key.M -> Shortcut.Memory
        else -> navKey(event)?.let(Shortcut::Nav)
    }
}

/** 키 입력을 레이어 0 동작으로. 입력이 없는 키는 null. */
private fun navKey(event: KeyEvent): NavKey? {
    if (event.isMetaPressed || event.isCtrlPressed) {
        return when (event.key) {
            Key.One -> NavKey.FOCUS_SPACES
            Key.Two -> NavKey.FOCUS_LIST
            Key.Three -> NavKey.FOCUS_PAGE
            Key.N -> NavKey.NEW_PAGE
            else -> null
        }
    }
    if (event.isAltPressed || event.isShiftPressed) return null
    return when (event.key) {
        Key.DirectionUp -> NavKey.UP
        Key.DirectionDown -> NavKey.DOWN
        Key.DirectionLeft -> NavKey.LEFT
        Key.DirectionRight -> NavKey.RIGHT
        Key.Enter, Key.NumPadEnter -> NavKey.ENTER
        Key.Backspace -> NavKey.BACK
        else -> null
    }
}

@Composable
private fun StatusLine(state: MainState) {
    val strings = LocalStrings.current
    val link = when (val current = state.link) {
        EventLink.Connecting -> strings.eventsConnecting
        EventLink.Live -> strings.eventsLive
        is EventLink.Retrying -> "${strings.eventsRetrying} (${current.retryIn})"
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            state.loadError.orEmpty(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.weight(1f)
        )
        Box {
            Text(
                "$link · core ${state.baseUrl}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
