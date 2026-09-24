package madang.shared.main

import kotlin.time.TimeSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.updateAndGet
import kotlinx.coroutines.launch
import madang.api.client.BlocksApi
import madang.api.client.DecisionsApi
import madang.api.client.MemoryApi
import madang.api.client.MessagesApi
import madang.api.client.PagesApi
import madang.api.client.ProjectsApi
import madang.api.client.RunsApi
import madang.api.client.TrashApi
import madang.api.model.BlockAddedEvent
import madang.api.model.BlockDeletedEvent
import madang.api.model.BlockType
import madang.api.model.BlockUpdatedEvent
import madang.api.model.DecisionAnswer
import madang.api.model.FlowWaitingData
import madang.api.model.FlowWaitingEvent
import madang.api.model.MemoryUpdatedEvent
import madang.api.model.MessageCreate
import madang.api.model.PageCard
import madang.api.model.PageCreate
import madang.api.model.PageCreatedEvent
import madang.api.model.PageDeletedEvent
import madang.api.model.PageUnknownFilesEvent
import madang.api.model.PageUpdate
import madang.api.model.PageUpdatedEvent
import madang.api.model.Project
import madang.api.model.ProjectCreate
import madang.api.model.ProjectCreatedEvent
import madang.api.model.ProjectDeletedEvent
import madang.api.model.ProjectSort
import madang.api.model.ProjectUpdate
import madang.api.model.ProjectUpdatedEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunStartedEvent
import madang.api.model.Target
import madang.api.model.UnknownFile
import madang.api.model.UnknownFileAction
import madang.shared.core.CoreClient
import madang.shared.core.CoreEvent
import madang.shared.core.EventStream
import madang.shared.core.EventStreamItem
import madang.shared.core.bodyOrThrow
import madang.shared.core.resolveUnknownFile
import madang.shared.settings.AppSettingsStore
import madang.shared.settings.InMemorySettingsStore

/**
 * 메인 화면(프로젝트 / 페이지 목록 / 가운데 열).
 *
 * 프로젝트는 core에 등록한 로컬 폴더이고 페이지 기록은 그 폴더의 `.madang/`에 있다.
 * 연결이 열릴 때마다 프로젝트와 모든 페이지 카드를 다시 받고, 이후에는 이벤트로 고친다.
 * 사용자 조작은 core에 요청하고 core의 응답(수정된 프로젝트·카드)으로 상태를 고친다. 응답과 같은
 * 내용의 이벤트가 다시 와도 id로 덮어쓰므로 결과가 같다. 낙관적 갱신은 보낸 메시지뿐이다.
 *
 * 가운데 열은 페이지 탭과 doc·data·run 탭이다. 탭 세트는 페이지마다 앱 설정에 저장해 두고
 * 페이지를 열 때 되살린다. 입력창([composer])은 활성 탭에게 보내고, 오른쪽 사이드바의 메모리
 * 탭([memory])과 최근 삭제([trash])는 열린 페이지를 따라간다.
 *
 * @param newPageTitle 새 페이지의 처음 제목.
 * @param settings 페이지별 탭 세트를 저장하는 앱 설정.
 */
class MainViewModel(
    private val core: CoreClient,
    events: EventStream,
    private val scope: CoroutineScope,
    private val newPageTitle: String = "Untitled",
    private val settings: AppSettingsStore = InMemorySettingsStore(),
    private val timeSource: TimeSource = TimeSource.Monotonic
) {
    private val _state = MutableStateFlow(MainState(baseUrl = core.baseUrl))
    val state: StateFlow<MainState> = _state.asStateFlow()

    private val projectsApi = core.api(::ProjectsApi)
    private val pagesApi = core.api(::PagesApi)
    private val blocksApi = core.api(::BlocksApi)
    private val runsApi = core.api(::RunsApi)
    private val messagesApi = core.api(::MessagesApi)
    private val decisionsApi = core.api(::DecisionsApi)
    private var pendingCount = 0

    val composer = ComposerViewModel(messagesApi, scope)
    val memory = MemoryViewModel(core.api(::MemoryApi), scope)
    val trash = TrashViewModel(core.api(::TrashApi), scope, onRestored = ::reloadAll)

    init {
        scope.launch { events.items().collect(::onItem) }
        scope.launch {
            state.map { it.page?.detail?.id }.distinctUntilChanged().collect { onOpenPageChanged() }
        }
        scope.launch {
            state.map { it.sendTarget }.distinctUntilChanged().collect(composer::setTarget)
        }
    }

    fun onKey(key: NavKey) {
        val outcome = _state.value.onKey(key)
        _state.value = outcome.state
        when (val effect = outcome.effect) {
            is KeyEffect.OpenPage -> loadPage(effect.id)
            KeyEffect.NewPage -> newPage()
            null -> Unit
        }
    }

    fun focusPane(pane: Pane) = _state.update { it.copy(pane = pane) }

    /** 1열 항목을 고른다. [advance]면 목록 열로 넘어간다(열이 모자랄 때). */
    fun select(source: ListSource, advance: Boolean = false) = _state.update {
        it.copy(source = source, pane = if (advance) Pane.LIST else Pane.PROJECTS)
    }

    fun toggleProject(id: String) = _state.update {
        val open = it.expandedProjects
        it.copy(expandedProjects = if (id in open) open - id else open + id)
    }

    fun toggleTag(path: String) = _state.update {
        val open = it.expandedTags
        it.copy(expandedTags = if (path in open) open - path else open + path)
    }

    /** 프로젝트 포커스. null이면 해제한다. */
    fun focusOn(id: String?) = _state.update {
        it.copy(
            focusProject = id,
            source = id?.let(ListSource::InProject) ?: it.source,
            expandedProjects = id?.let { s -> it.expandedProjects + s } ?: it.expandedProjects
        )
    }

    fun setFilter(filter: PageFilter) = _state.update { it.copy(filter = filter) }

    /** 고른 프로젝트의 정렬을 바꾼다. 태그를 보고 있으면 바꿀 프로젝트가 없다. */
    fun setSort(sort: ProjectSort) {
        val id = (_state.value.source as? ListSource.InProject)?.id ?: return
        request {
            upsertProject(projectsApi.updateProject(id, ProjectUpdate(sort = sort)).bodyOrThrow())
        }
    }

    /** 페이지를 고르고 연다. [advance]면 본문 열로 넘어간다(열이 모자랄 때). */
    fun openPage(id: String, advance: Boolean = false) {
        _state.update { it.copy(selectedPage = id, pane = if (advance) Pane.PAGE else Pane.LIST) }
        loadPage(id)
    }

    /** 흐름 항목을 클릭했다. doc·data·run이면 탭을 연다(이미 열려 있으면 그 탭으로). */
    fun openItem(item: FlowItem) {
        tabFor(item)?.let(::openTab)
    }

    fun openTab(tab: BlockTab) {
        updateTabs { it.open(tab) }
        if (tab is BlockTab.Run) _state.value.page?.detail?.id?.let { loadRunEvents(it, tab.n) }
    }

    /** 탭을 고른다. null은 페이지 탭. */
    fun activateTab(tab: BlockTab?) = updateTabs { it.activate(tab) }

    fun closeTab(tab: BlockTab) = updateTabs { it.close(tab) }

    fun onTabKey(key: TabKey) = updateTabs {
        when (key) {
            TabKey.CLOSE -> it.closeActive()
            TabKey.NEXT -> it.next()
            TabKey.PREVIOUS -> it.previous()
            TabKey.PAGE -> it.activate(null)
        }
    }

    fun toggleExpandAll() = _state.update {
        it.copy(expandAll = !it.expandAll, toggled = emptySet())
    }

    fun toggleFold(key: String) = _state.update {
        it.copy(toggled = if (key in it.toggled) it.toggled - key else it.toggled + key)
    }

    /** 고른 프로젝트에 새 페이지를 만든다. 등록한 프로젝트가 없으면 아무것도 하지 않는다. */
    fun newPage() {
        val project = _state.value.targetProject ?: return
        request {
            val created = pagesApi.createPage(project, PageCreate(title = newPageTitle))
                .bodyOrThrow()
            val cards = pagesApi.listPages(project).bodyOrThrow()
            _state.update { state ->
                state.copy(
                    cards = state.cards.filter { it.project != project } + cards,
                    source = state.source as? ListSource.InProject
                        ?: ListSource.InProject(project),
                    selectedPage = created.id,
                    page = OpenPage(created),
                    tabs = TabSet(),
                    pane = Pane.PAGE
                )
            }
        }
    }

    /** 로컬 폴더를 프로젝트로 등록하고 고른다. core가 폴더에 `.madang/`을 만든다. */
    fun addProject(path: String) = request {
        val project = projectsApi.createProject(ProjectCreate(path = path)).bodyOrThrow()
        upsertProject(project)
        _state.update { it.copy(source = ListSource.InProject(project.id)) }
    }

    fun renameProject(id: String, title: String) = updateProject(id, ProjectUpdate(title = title))

    /** 프로젝트 등록을 지운다. 폴더와 그 안의 기록은 그대로 남는다. */
    fun removeProject(id: String) = request {
        projectsApi.deleteProject(id).bodyOrThrow()
        forgetProject(id)
    }

    fun setPinned(id: String, pinned: Boolean) = updatePage(id, PageUpdate(pinned = pinned))

    fun setTags(id: String, tags: List<String>) = updatePage(id, PageUpdate(tags = tags.distinct()))

    /** 페이지에 태그 하나를 더한다(태그로 끌어다 놓기). */
    fun addTag(id: String, tag: String) {
        val card = _state.value.cards.firstOrNull { it.id == id } ?: return
        if (tag !in card.tags) setTags(id, card.tags + tag)
    }

    fun movePage(id: String, project: String) {
        val card = _state.value.cards.firstOrNull { it.id == id } ?: return
        if (card.project != project) updatePage(id, PageUpdate(project = project))
    }

    fun deletePage(id: String) = request {
        pagesApi.deletePage(id).bodyOrThrow()
        removeCard(id)
    }

    /** 열린 페이지의 진행 중인 run을 멈춘다. 끝남은 `run.failed` 이벤트로 온다. */
    fun cancelRun() {
        val state = _state.value
        val run = state.page?.detail?.id?.let { state.activeRuns[it] } ?: return
        request { runsApi.cancelRun(run.page, run.n).bodyOrThrow() }
    }

    /**
     * 입력창의 문장을 활성 탭(페이지 또는 블록)에게 보낸다. 메시지는 core 응답 전에 본문 끝에
     * 붙인다.
     */
    fun send() {
        if (_state.value.page == null) return
        val (target, text) = composer.take() ?: return
        val page = target.page
        val message = MessageCreate(text, target = target.block?.let { Target(block = it) })
        val pending = PendingMessage("pending-${++pendingCount}", text)
        updateOpen(page) { it.copy(pending = it.pending + pending) }
        scope.launch {
            try {
                val accepted = messagesApi.sendMessage(page, message).bodyOrThrow()
                updateOpen(page) { it.withAccepted(pending.localId, accepted.message) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                updateOpen(page) { open ->
                    open.copy(pending = open.pending.filter { it.localId != pending.localId })
                }
                composer.restore(page, text)
                showError(e)
            }
        }
    }

    /** 사이드바의 메모리 탭을 열거나 닫는다(M). 다른 탭이 보이고 있으면 메모리 탭으로 바꾼다. */
    fun toggleMemory() {
        val sidebar = _state.value.sidebar
        showSidebar(if (sidebar.showsMemory) sidebar.copy(open = false) else Sidebar(true))
    }

    fun selectSideTab(tab: SideTab) = showSidebar(Sidebar(open = true, tab = tab))

    fun closeSidebar() = showSidebar(_state.value.sidebar.copy(open = false))

    private fun showSidebar(sidebar: Sidebar) {
        _state.update { it.copy(sidebar = sidebar) }
        syncMemory()
    }

    /** 메모리 탭이 보이고 페이지가 열려 있을 때만 그 페이지의 메모리를 받는다. */
    private fun syncMemory() {
        val state = _state.value
        val page = state.page?.detail?.id
        if (state.sidebar.showsMemory && page != null) memory.open(page) else memory.close()
    }

    fun showUnknownFiles(show: Boolean) = _state.update {
        it.copy(unknownFilesOpen = show && !it.page?.detail?.unknownFiles.isNullOrEmpty())
    }

    /** 미등록 파일 하나를 산출물로 등록·유지·삭제한다. 남은 목록은 core 응답으로 바꾼다. */
    fun resolveUnknownFile(path: String, action: UnknownFileAction.Action) {
        val page = _state.value.page?.detail?.id ?: return
        request {
            setUnknownFiles(page, core.resolveUnknownFile(page, path, UnknownFileAction(action)))
        }
    }

    /** 열린 페이지가 기다리는 사람 결정에 답한다. flow가 다시 돌면 카드가 사라진다. */
    fun answer(choice: String) {
        val open = _state.value.page ?: return
        val decision = open.detail.waiting?.decision ?: return
        if (open.answered == decision.id) return
        val page = open.detail.id
        updateOpen(page) { it.copy(answered = decision.id) }
        scope.launch {
            try {
                decisionsApi.answerDecision(page, decision.id, DecisionAnswer(choice))
                    .bodyOrThrow()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                updateOpen(page) {
                    if (it.answered == decision.id) it.copy(answered = null) else it
                }
                showError(e)
            }
        }
    }

    private fun onOpenPageChanged() {
        _state.update { it.copy(unknownFilesOpen = false) }
        syncMemory()
    }

    private fun onItem(item: EventStreamItem) {
        when (item) {
            is EventStreamItem.Resync -> {
                _state.update { it.copy(link = EventLink.Live) }
                reloadAll()
            }

            is EventStreamItem.Disconnected ->
                _state.update { it.copy(link = EventLink.Retrying(item.cause, item.retryIn)) }

            is EventStreamItem.Received -> applyEvent(item.event)
        }
    }

    private fun applyEvent(event: CoreEvent) {
        val payload = event.payload
        _state.update {
            it.copy(activeRuns = it.activeRuns.withRunEvent(payload, timeSource::markNow))
        }
        when (payload) {
            is ProjectCreatedEvent -> upsertProject(payload.data.project)

            is ProjectUpdatedEvent -> upsertProject(payload.data.project)

            is ProjectDeletedEvent -> forgetProject(payload.data.id)

            is PageCreatedEvent -> upsertCard(payload.data.page)

            is PageUpdatedEvent -> upsertCard(payload.data.page).also {
                refreshIfOpen(payload.page)
            }

            is PageDeletedEvent -> removeCard(payload.data.id)

            is BlockAddedEvent, is BlockUpdatedEvent, is BlockDeletedEvent,
            is RunFinishedEvent, is RunFailedEvent -> refreshIfOpen(event.envelope.page)

            is RunStartedEvent -> setWaiting(payload.page, null)

            is PageUnknownFilesEvent -> setUnknownFiles(payload.page, payload.data.files)

            is FlowWaitingEvent -> setWaiting(payload.page, payload.data)

            is MemoryUpdatedEvent -> memory.onUpdated(payload.page, payload.data.layer)
        }
    }

    private fun reloadAll() = request {
        val projects = projectsApi.listProjects().bodyOrThrow()
        val cards = projects.flatMap { pagesApi.listPages(it.id).bodyOrThrow() }
        _state.update { it.withLoaded(projects, cards) }
        _state.value.selectedPage?.let(::loadPage)
    }

    private fun refreshIfOpen(page: String?) {
        if (page != null && _state.value.page?.detail?.id == page) loadPage(page)
    }

    /**
     * 페이지와 doc·data 블록 내용을 불러온다. 그사이 다른 페이지를 골랐으면 버린다. 새로 여는
     * 페이지면 저장해 둔 탭 세트를 되살리고, 사라진 블록·run의 탭은 닫는다. 열린 run 탭의
     * 이벤트 로그도 다시 받는다.
     */
    private fun loadPage(id: String) = request {
        val detail = pagesApi.getPage(id).bodyOrThrow()
        if (_state.value.selectedPage != id) return@request
        val tabs = _state.updateAndGet { state ->
            val open = state.page?.takeIf { it.detail.id == id }
            val toggled = if (open != null) state.toggled else emptySet()
            val tabs = if (open != null) state.tabs else savedTabs(id)
            state.copy(
                page = open?.withDetail(detail) ?: OpenPage(detail),
                tabs = tabs.retainIn(detail),
                toggled = toggled
            )
        }.tabs
        saveTabs(id, tabs)
        tabs.tabs.filterIsInstance<BlockTab.Run>().forEach { loadRunEvents(id, it.n) }
        val contents = detail.blocks
            .filter { it.type == BlockType.DOC || it.type == BlockType.DATA }
            .associate { it.id to blocksApi.getBlock(id, it.id).bodyOrThrow().content }
        updateOpen(id) { it.copy(contents = contents) }
    }

    /** run 탭의 이벤트 로그(`GET /pages/{p}/runs/{n}/events`)를 받는다. */
    private fun loadRunEvents(page: String, n: Int) = request {
        val events = runsApi.listRunEvents(page, n).bodyOrThrow()
        updateOpen(page) { it.copy(runEvents = it.runEvents + (n to events)) }
    }

    /** 열린 페이지의 탭 세트를 바꾸고 앱 설정에 저장한다. 열린 페이지가 없으면 무시한다. */
    private fun updateTabs(change: (TabSet) -> TabSet) {
        val page = _state.value.page?.detail?.id ?: return
        val next = _state.updateAndGet { state ->
            if (state.page?.detail?.id == page) state.copy(tabs = change(state.tabs)) else state
        }
        if (next.page?.detail?.id == page) saveTabs(page, next.tabs)
    }

    private fun savedTabs(page: String): TabSet = settings.load().pageTabs[page] ?: TabSet()

    /** 페이지 탭만 남은 세트는 기록하지 않는다. 같은 값이면 파일을 다시 쓰지 않는다. */
    private fun saveTabs(page: String, tabs: TabSet?) {
        val current = settings.load()
        val stored = current.pageTabs[page]
        val next = tabs?.takeIf { it != TabSet() }
        if (stored == next) return
        val pageTabs = if (next ==
            null
        ) {
            current.pageTabs - page
        } else {
            current.pageTabs + (page to next)
        }
        settings.save(current.copy(pageTabs = pageTabs))
    }

    /** 열린 페이지가 [page]일 때만 고친다. */
    private fun updateOpen(page: String?, change: (OpenPage) -> OpenPage) = _state.update { state ->
        val open = state.page?.takeIf { it.detail.id == page } ?: return@update state
        state.copy(page = change(open))
    }

    private fun setUnknownFiles(page: String, files: List<UnknownFile>) {
        updateOpen(page) { it.copy(detail = it.detail.copy(unknownFiles = files)) }
        if (files.isEmpty()) _state.update { it.copy(unknownFilesOpen = false) }
    }

    /** flow 대기 상태를 바꾼다. 새 질문이 오거나 flow가 다시 돌면 보낸 답 표시를 지운다. */
    private fun setWaiting(page: String, waiting: FlowWaitingData?) = updateOpen(page) {
        it.copy(detail = it.detail.copy(waiting = waiting), answered = null)
    }

    private fun updateProject(id: String, update: ProjectUpdate) = request {
        upsertProject(projectsApi.updateProject(id, update).bodyOrThrow())
    }

    private fun updatePage(id: String, update: PageUpdate) = request {
        upsertCard(pagesApi.updatePage(id, update).bodyOrThrow())
    }

    private fun upsertProject(project: Project) = _state.update { state ->
        val others = state.projects.filter { it.id != project.id }
        state.copy(projects = others + project)
    }

    /** 등록이 지워진 프로젝트와 그 카드를 목록에서 뺀다. */
    private fun forgetProject(id: String) = _state.update { state ->
        state.withLoaded(
            state.projects.filter { it.id != id },
            state.cards.filter { it.project != id }
        )
    }

    private fun upsertCard(card: PageCard) = _state.update { state ->
        val index = state.cards.indexOfFirst { it.id == card.id }
        val cards = if (index < 0) {
            state.cards + card
        } else {
            state.cards.toMutableList().also { it[index] = card }
        }
        state.copy(cards = cards)
    }

    private fun removeCard(id: String) {
        _state.update { state ->
            val closing = state.selectedPage == id
            state.copy(
                cards = state.cards.filter { it.id != id },
                selectedPage = state.selectedPage.takeUnless { closing },
                page = state.page.takeUnless { closing },
                tabs = if (closing) TabSet() else state.tabs,
                pane = if (closing && state.pane == Pane.PAGE) Pane.LIST else state.pane
            )
        }
        saveTabs(id, null)
    }

    /** core 요청을 띄운다. 실패하면 상태 줄에 원인을 보인다. */
    private fun request(block: suspend () -> Unit) {
        scope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                showError(e)
            }
        }
    }

    private fun showError(e: Exception) =
        _state.update { it.copy(loadError = e.message ?: e::class.simpleName) }
}
