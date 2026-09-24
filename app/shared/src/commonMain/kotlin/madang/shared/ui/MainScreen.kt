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
import androidx.compose.runtime.rememberCoroutineScope
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
import kotlinx.coroutines.launch
import madang.shared.LocalFolderPicker
import madang.shared.main.EventLink
import madang.shared.main.MainState
import madang.shared.main.MainViewModel
import madang.shared.main.NavKey
import madang.shared.main.Pane
import madang.shared.main.TabKey
import madang.shared.main.visiblePanes

/**
 * 메인 화면: 3열(프로젝트 / 페이지 목록 / 탭이 있는 가운데 열)과 아래 상태 줄.
 *
 * 입력창이나 메모리 편집기에 포커스가 있으면 글자·화살표 키는 그쪽이 받고, Cmd/Ctrl 단축키와
 * Esc만 화면이 받는다. 탭 단축키: Cmd/Ctrl+W 탭 닫기, Cmd/Ctrl+Shift+]/[ 다음/이전 탭,
 * Cmd/Ctrl+1 페이지 탭, Esc 페이지 탭으로.
 */
@Composable
fun MainScreen(viewModel: MainViewModel, onOpenSettings: () -> Unit) {
    val state by viewModel.state.collectAsState()
    val composer by viewModel.composer.state.collectAsState()
    val memory by viewModel.memory.state.collectAsState()
    val strings = LocalStrings.current.navigator
    val folderPicker = LocalFolderPicker.current
    val scope = rememberCoroutineScope()
    val focus = remember { FocusRequester() }
    var dialog by remember { mutableStateOf<MainDialog?>(null) }
    var editing by remember { mutableStateOf(false) }
    var drawerOpen by remember { mutableStateOf(true) }
    var origin by remember { mutableStateOf(Offset.Zero) }
    val drag = remember(viewModel) {
        DragDropState { card, target ->
            when (target) {
                is DropTarget.ToProject -> viewModel.movePage(card.id, target.id)
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

                        is Shortcut.Tab -> true.also {
                            viewModel.onTabKey(shortcut.key)
                            if (shortcut.key == TabKey.PAGE && shortcut.focusPage) {
                                viewModel.focusPane(Pane.PAGE)
                            }
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
                            Pane.PROJECTS -> ProjectsColumn(
                                state,
                                projectsActions(
                                    viewModel,
                                    state,
                                    panes,
                                    onOpenSettings,
                                    addProject = {
                                        scope.launch {
                                            folderPicker.pick(strings.chooseProjectFolder)
                                                ?.let(viewModel::addProject)
                                        }
                                    }
                                ) { dialog = it },
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
                                    TabActions(
                                        activate = viewModel::activateTab,
                                        close = viewModel::closeTab,
                                        drawerOpen = drawerOpen,
                                        toggleDrawer = { drawerOpen = !drawerOpen }
                                    ),
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
                    is DropTarget.ToProject -> strings.dropToMove(
                        state.projects.firstOrNull { it.id == target.id }?.title ?: target.id
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
    pane == Pane.PROJECTS && count == 3 -> Modifier.width(240.dp).fillMaxHeight()
    pane == Pane.PAGE -> Modifier.fillMaxHeight().fillMaxWidth()
    else -> Modifier.width(340.dp).fillMaxHeight()
}

private fun projectsActions(
    viewModel: MainViewModel,
    state: MainState,
    panes: List<Pane>,
    onOpenSettings: () -> Unit,
    addProject: () -> Unit,
    show: (MainDialog) -> Unit
) = ProjectsActions(
    select = { viewModel.select(it, advance = Pane.LIST !in panes) },
    toggleProject = viewModel::toggleProject,
    toggleTag = viewModel::toggleTag,
    collapseAll = { state.expandedProjects.forEach(viewModel::toggleProject) },
    focusOn = viewModel::focusOn,
    addProject = addProject,
    rename = { show(MainDialog.RenameProject(it.project.id, it.project.title)) },
    remove = { show(MainDialog.RemoveProject(it.project.id, it.project.title)) },
    openTrash = { show(MainDialog.Trash) },
    openSettings = onOpenSettings
)

private fun pageActions(
    viewModel: MainViewModel,
    panes: List<Pane>,
    tabs: TabActions,
    onEditing: (Boolean) -> Unit,
    onEscape: () -> Unit
) = PageActions(
    toggleExpandAll = viewModel::toggleExpandAll,
    toggleFold = viewModel::toggleFold,
    openItem = viewModel::openItem,
    tabs = tabs,
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
        move = { card, project -> viewModel.movePage(card.id, project) },
        delete = { show(MainDialog.DeletePage(it.id, it.title)) },
        back = { viewModel.focusPane(Pane.PROJECTS) }.takeIf { Pane.PROJECTS !in panes }
    )

/** 메인 화면이 가로채는 키. */
private sealed interface Shortcut {
    data object Search : Shortcut

    data object Memory : Shortcut

    data object CloseMemory : Shortcut

    data class Nav(val key: NavKey) : Shortcut

    /** 탭 동작. [focusPage]면 가운데 열로 키보드 포커스도 옮긴다(Cmd/Ctrl+1). */
    data class Tab(val key: TabKey, val focusPage: Boolean = false) : Shortcut
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
        plain && event.key == Key.Escape -> Shortcut.Tab(TabKey.PAGE)
        plain && event.key == Key.M -> Shortcut.Memory
        command -> tabKey(event) ?: navKey(event)?.let(Shortcut::Nav)
        else -> navKey(event)?.let(Shortcut::Nav)
    }
}

/** Cmd/Ctrl 키 입력을 탭 동작으로. 탭 단축키가 아니면 null. */
private fun tabKey(event: KeyEvent): Shortcut.Tab? = when {
    event.key == Key.W && !event.isShiftPressed -> Shortcut.Tab(TabKey.CLOSE)
    event.key == Key.RightBracket && event.isShiftPressed -> Shortcut.Tab(TabKey.NEXT)
    event.key == Key.LeftBracket && event.isShiftPressed -> Shortcut.Tab(TabKey.PREVIOUS)
    event.key == Key.One && !event.isShiftPressed -> Shortcut.Tab(TabKey.PAGE, focusPage = true)
    else -> null
}

/**
 * 키 입력을 레이어 0 동작으로. 입력이 없는 키는 null. Cmd/Ctrl+1은 탭 단축키가 쓰고,
 * Cmd/Ctrl+0은 프로젝트 열로 간다.
 */
private fun navKey(event: KeyEvent): NavKey? {
    if (event.isMetaPressed || event.isCtrlPressed) {
        return when (event.key) {
            Key.Zero -> NavKey.FOCUS_PROJECTS
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
