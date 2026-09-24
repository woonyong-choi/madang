package madang.shared.main

import kotlin.time.TimeSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.updateAndGet
import kotlinx.coroutines.launch
import madang.api.client.BlocksApi
import madang.api.client.DecisionsApi
import madang.api.client.GitApi
import madang.api.client.MessagesApi
import madang.api.client.PagesApi
import madang.api.client.ProjectsApi
import madang.api.client.RunsApi
import madang.api.client.SetupApi
import madang.api.client.TrashApi
import madang.api.client.ViewersApi
import madang.api.model.BlockAddedEvent
import madang.api.model.BlockContent
import madang.api.model.BlockDeletedEvent
import madang.api.model.BlockUpdatedEvent
import madang.api.model.DecisionAnswer
import madang.api.model.FlowWaitingData
import madang.api.model.FlowWaitingEvent
import madang.api.model.GitChangedEvent
import madang.api.model.Issue
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
import madang.api.model.RunsOpenedEvent
import madang.api.model.Target
import madang.api.model.UnknownFile
import madang.api.model.UnknownFileAction
import madang.shared.LocalFiles
import madang.shared.NoLocalFiles
import madang.shared.core.CoreApiException
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
 * 가운데 열은 페이지 탭과 블록·run·브라우저·디프·파일 탭이다. 무엇을 열지는 열기 요청
 * ([OpenRequest])과 파일 확장자로만 정한다([tabKindOf]). 탭 세트는 페이지마다 앱 설정에 저장해 두고
 * 페이지를 열 때 되살린다. 입력창([composer])은 활성 탭에게 보내고, 오른쪽 사이드바 탭([side])은
 * 열린 페이지와 그 프로젝트를 따라간다.
 *
 * run 이벤트로 페이지별 실행 상태([MainState.watch])를 따라가고, 앱 설정이 허락하면 run 완료·실패와
 * 묻는 블록을 [notices]로 알린다. 읽지 않음은 앱 설정에 저장해 재시작 뒤에도 남는다.
 *
 * 사용자가 누르는 실행은 보내기 하나다. 머지·게시는 core 정책이 하고, 앱은 결과 블록에 그 상태
 * ([OpenPage.outcome])와 되돌리기·다시 실행을, 정책이 멈추면 묻는 블록의 선택지를 보인다. 모두
 * core API를 부른다.
 *
 * @param newPageTitle 새 페이지의 처음 제목.
 * @param settings 페이지별 탭 세트를 저장하는 앱 설정.
 * @param files 파일 탭이 작업 폴더 파일을 읽고 외부 앱으로 여는 곳.
 */
class MainViewModel(
    private val core: CoreClient,
    events: EventStream,
    private val scope: CoroutineScope,
    private val newPageTitle: String = "Untitled",
    private val settings: AppSettingsStore = InMemorySettingsStore(),
    private val timeSource: TimeSource = TimeSource.Monotonic,
    private val files: LocalFiles = NoLocalFiles
) {
    private val _state = MutableStateFlow(
        MainState(baseUrl = core.baseUrl, watch = RunWatch(unread = settings.load().unread))
    )
    val state: StateFlow<MainState> = _state.asStateFlow()

    private val projectsApi = core.api(::ProjectsApi)
    private val pagesApi = core.api(::PagesApi)
    private val blocksApi = core.api(::BlocksApi)
    private val runsApi = core.api(::RunsApi)
    private val messagesApi = core.api(::MessagesApi)
    private val decisionsApi = core.api(::DecisionsApi)
    private val gitApi = core.api(::GitApi)
    private val viewersApi = core.api(::ViewersApi)
    private val setupApi = core.api(::SetupApi)
    private val documents = DocumentViews(
        listViewers = { viewersApi.listViewers(it).bodyOrThrow() },
        home = { setupApi.getHome().bodyOrThrow().path },
        files = files
    )
    private var pendingCount = 0

    private val _notices = MutableSharedFlow<Notice>(extraBufferCapacity = NOTICE_BUFFER)
    private val notifiedDecisions = mutableSetOf<String>()

    /** 시스템 알림으로 띄울 것. 앱 설정에서 알림을 끄면 오지 않는다. */
    val notices: SharedFlow<Notice> = _notices

    val composer = ComposerViewModel(messagesApi, scope)
    val side = SidebarTabs(core, scope)
    val memory: MemoryViewModel get() = side.memory
    val trash = TrashViewModel(core.api(::TrashApi), scope, onRestored = ::reloadAll)

    init {
        scope.launch { events.items().collect(::onItem) }
        scope.launch {
            state.map { it.page?.detail?.id }.distinctUntilChanged().collect { onOpenPageChanged() }
        }
        scope.launch {
            state.map { it.sendTarget }.distinctUntilChanged().collect(composer::setTarget)
        }
        scope.launch {
            state.map { it.watch.unread }.distinctUntilChanged().collect(::saveUnread)
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

    /**
     * 흐름 항목을 더블클릭했다. run·블록을 그 종류의 탭으로 연다(이미 열려 있으면 그 탭으로). code
     * 블록의 `path`는 작업 폴더 기준이라 core에 작업 폴더를 물어 절대 경로로 연다.
     */
    fun openItem(item: FlowItem) {
        when (val target = openTargetFor(item)) {
            is OpenTarget.Tab -> openTab(target.tab)

            is OpenTarget.Request -> when (val request = target.request) {
                is OpenRequest.File -> openWorkFile(request.path)
                else -> open(request)
            }

            null -> Unit
        }
    }

    /**
     * 열기 요청을 탭 종류 규칙([tabKindOf])대로 연다. 파일은 절대 경로다. `.html` 파일은 브라우저
     * 탭, 나머지 파일은 파일 탭이다. 터미널·채팅 탭은 아직 없어서 열지 않는다.
     */
    fun open(request: OpenRequest) {
        when (request) {
            is OpenRequest.File -> openTab(
                if (tabKindOf(request) == TabKind.BROWSER) {
                    CenterTab.Browser(fileUrl(request.path))
                } else {
                    CenterTab.File(request.path)
                }
            )

            is OpenRequest.Url -> openTab(CenterTab.Browser(request.url))

            OpenRequest.Diff -> openTab(CenterTab.Diff)

            OpenRequest.Terminal, OpenRequest.Chat -> Unit
        }
    }

    fun openTab(tab: CenterTab) {
        updateTabs { it.open(tab) }
        _state.value.page?.detail?.let { loadTab(it.id, it.project, tab) }
    }

    /** 디프 탭 내용을 다시 받는다. */
    fun reloadDiff() {
        val page = _state.value.page?.detail ?: return
        loadDiff(page.id, page.project)
    }

    /** 파일이나 URL을 운영체제의 기본 앱으로 연다(코드 보기의 "외부 편집기로 열기"). */
    fun openExternally(target: String) = files.openExternally(target)

    /**
     * 문서 탭에서 누른 링크를 연다. 실행 블록은 run 탭, 블록 "열기"는 그 블록을 흐름에서 연 것과
     * 같고, 나머지 링크는 [linkTarget] 규칙대로 연다(view 펜스의 "데이터" 링크는 데이터 탭).
     *
     * @param documentDir 링크가 적힌 문서의 폴더. 상대 경로의 기준이다.
     */
    fun openDocumentRequest(request: DocumentRequest, documentDir: String?) {
        when (request) {
            is DocumentRequest.Run -> openTab(CenterTab.Run(request.n))

            is DocumentRequest.Block -> {
                val block = _state.value.page?.detail?.blocks?.firstOrNull { it.id == request.id }
                    ?.let { FlowItem.Block(it) }
                if (block != null && openTargetFor(block) != null) {
                    openItem(block)
                } else {
                    openLink(request.href, documentDir)
                }
            }

            is DocumentRequest.Link -> openLink(request.href, documentDir)
        }
    }

    /**
     * 문서의 view 펜스를 렌더러 context로 푼다. 열린 페이지의 프로젝트 뷰어가 먼저다.
     *
     * @param documentDir 문서의 폴더. `data=` 경로의 기준이다.
     */
    suspend fun documentViews(markdown: String, documentDir: String?): Map<String, ViewEntry> =
        documents.resolve(markdown, documentDir, _state.value.page?.detail?.project)

    /** 데이터 탭에서 블록 원문을 고친다. */
    fun editData(block: String, text: String) {
        val page = _state.value.page?.detail?.id ?: return
        updateOpen(page) {
            val draft = it.drafts[block] ?: DataDraft(text)
            it.copy(drafts = it.drafts + (block to draft.copy(text = text, error = null)))
        }
    }

    /** 고치던 원문을 버리고 저장된 내용으로 돌아간다. */
    fun discardData(block: String) {
        val page = _state.value.page?.detail?.id ?: return
        updateOpen(page) { it.copy(drafts = it.drafts - block) }
    }

    /**
     * 고친 원문을 core에 저장한다(`PUT /pages/{p}/blocks/{b}`). core가 형식을 검사해 거부하면(400)
     * 이유를 줄 옆에 보인다.
     */
    fun saveData(block: String) {
        val page = _state.value.page?.detail?.id ?: return
        val draft = _state.value.page?.drafts?.get(block)?.takeIf { !it.saving } ?: return
        updateDraft(page, block) { it.copy(saving = true, error = null) }
        scope.launch {
            try {
                val saved = blocksApi.replaceBlock(page, block, BlockContent(draft.text))
                    .bodyOrThrow()
                updateOpen(page) { open ->
                    val now = open.drafts[block]
                    val drafts = if (now == null || now.text == draft.text) {
                        open.drafts - block
                    } else {
                        open.drafts + (block to now.copy(saving = false))
                    }
                    open.copy(contents = open.contents + (block to saved.content), drafts = drafts)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: CoreApiException) {
                val issues = e.issues.takeIf { e.status == HTTP_BAD_REQUEST }?.ifEmpty {
                    listOf(Issue(code = e.error?.error ?: "invalid", message = e.message ?: ""))
                }
                updateDraft(page, block) {
                    it.copy(
                        saving = false,
                        issues = issues.orEmpty(),
                        error = e.message.takeIf {
                            issues == null
                        }
                    )
                }
            } catch (e: Exception) {
                updateDraft(page, block) {
                    it.copy(saving = false, error = e.message ?: e::class.simpleName)
                }
            }
        }
    }

    /** 탭을 고른다. null은 페이지 탭. */
    fun activateTab(tab: CenterTab?) = updateTabs { it.activate(tab) }

    fun closeTab(tab: CenterTab) = updateTabs { it.close(tab) }

    fun onTabKey(key: TabKey) = updateTabs {
        when (key) {
            TabKey.CLOSE -> it.closeActive()
            TabKey.NEXT -> it.next()
            TabKey.PREVIOUS -> it.previous()
            TabKey.PAGE -> it.activate(null)
        }
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
        post(target.page, text, target.block) { composer.restore(target.page, text) }
    }

    /**
     * 결과 블록의 "다시 실행": 마지막으로 끝난 run을 일으킨 요청을 같은 대상에게 다시 보낸다.
     * 보내기와 같은 길(`POST /pages/{p}/messages`)이다.
     */
    fun rerun() {
        val open = _state.value.page ?: return
        if (open.detail.id in _state.value.activeRuns) return
        val trigger = lastFinishedRun(open.detail.runs)?.trigger?.message ?: return
        val request = open.detail.blocks.firstOrNull { it.id == trigger } ?: return
        val text = request.text?.takeIf { it.isNotBlank() } ?: return
        post(open.detail.id, text, request.target?.block)
    }

    /**
     * 결과 블록의 "되돌리기": core가 그 run의 부작용(게시·머지·커밋·페이지 파일)을 기록대로
     * 되감는다(`POST /pages/{p}/runs/{n}/undo`). core가 거부하면(409) 이유를 상태 줄에 보인다.
     */
    fun undo() {
        val open = _state.value.page ?: return
        val outcome = open.outcome ?: return
        if (open.undoing || outcome.undone) return
        val page = open.detail.id
        updateOpen(page) { it.copy(undoing = true, undoResult = null) }
        scope.launch {
            try {
                val result = runsApi.undoRun(page, outcome.n).bodyOrThrow()
                updateOpen(page) {
                    it.copy(
                        undoing = false,
                        undoResult = result,
                        settle = it.settle.copy(undone = it.settle.undone + outcome.n)
                    )
                }
                refreshIfOpen(page)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                updateOpen(page) { it.copy(undoing = false) }
                showError(e)
            }
        }
    }

    /**
     * 페이지에 요청을 보낸다. 메시지는 core 응답 전에 본문 끝에 붙인다. 실패하면 붙인 것을 빼고
     * [onFailed]를 부른다.
     */
    private fun post(page: String, text: String, block: String?, onFailed: () -> Unit = {}) {
        val message = MessageCreate(text, target = block?.let { Target(block = it) })
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
                onFailed()
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
        syncSidebar()
    }

    /** 보이는 사이드바 탭을 열린 페이지(없으면 고른 프로젝트)로 맞춘다. */
    private fun syncSidebar() {
        val state = _state.value
        val page = state.page?.detail
        side.sync(state.sidebar, page?.project ?: state.targetProject, page?.id)
    }

    /** 지금 탭의 줄을 누르지 않고 두 번 눌렀다: 그 페이지를 연다. */
    fun showPage(project: String, page: String) {
        select(ListSource.InProject(project))
        openPage(page, advance = true)
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

    /**
     * 열린 페이지가 기다리는 사람 결정에 답한다. 정책이 멈춘 묻는 블록이면 그 블록에
     * (`POST /pages/{p}/asks/{id}/answer`), 아니면 결정에 답한다. flow가 다시 돌면 카드가 사라진다.
     */
    fun answer(choice: String) {
        val open = _state.value.page ?: return
        val decision = open.detail.waiting?.decision ?: return
        if (open.answered == decision.id) return
        val page = open.detail.id
        updateOpen(page) { it.copy(answered = decision.id) }
        scope.launch {
            try {
                val ask = decision.ask
                if (ask != null) {
                    decisionsApi.answerAsk(page, ask, DecisionAnswer(choice)).bodyOrThrow()
                } else {
                    decisionsApi.answerDecision(page, decision.id, DecisionAnswer(choice))
                        .bodyOrThrow()
                }
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
        syncSidebar()
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
            it.copy(
                watch = it.watch.withEvent(payload, it.activeRuns, it.page?.detail?.id),
                activeRuns = it.activeRuns.withRunEvent(payload, timeSource::markNow)
            )
        }
        watchSettle(event)
        noticeOf(payload, _state.value::pageTitle)?.let(::notify)
        side.onEvent(payload)
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

            is RunsOpenedEvent -> openInProject(
                payload.project,
                CenterTab.Browser(payload.data.url)
            )

            is GitChangedEvent -> reloadDiffIn(payload.project)
        }
    }

    /** 열린 페이지의 정책 단계를 이벤트로 따라간다. 새 run이 시작하면 지난 되돌리기 결과를 지운다. */
    private fun watchSettle(event: CoreEvent) {
        val open = _state.value.page?.detail ?: return
        val page = event.envelope.page
        if (page != null && page != open.id) return
        val payload = event.payload
        updateOpen(open.id) {
            it.copy(
                settle = it.settle.withEvent(payload),
                undoResult = it.undoResult.takeUnless { payload is RunStartedEvent }
            )
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
            val tabs = if (open != null) state.tabs else savedTabs(id)
            state.copy(
                page = open?.withDetail(detail) ?: OpenPage(detail),
                tabs = tabs.retainIn(detail),
                watch = state.watch.read(id).withWaiting(id, detail.waiting != null)
            )
        }.tabs
        saveTabs(id, tabs)
        tabs.tabs.filterNot { it is CenterTab.Block }.forEach { loadTab(id, detail.project, it) }
        val contents = detail.blocks
            .filter { it.type in TAB_BLOCK_TYPES }
            .associate { it.id to blocksApi.getBlock(id, it.id).bodyOrThrow().content }
        val folder = _state.value.pageFolder
        val source = folder?.let { readOrNull(pageFile(it)) }
        val undoLog = folder?.let {
            lastFinishedRun(detail.runs)?.n?.let { n -> undoLogFile(it, n) }
        }
            ?.let { readOrNull(it) }
            ?.let(::parseUndoLog)
        updateOpen(id) { it.copy(contents = contents, source = source, undoLog = undoLog) }
    }

    /**
     * 탭이 따로 받는 내용을 받는다: run 탭은 이벤트 로그, 파일 탭은 파일, 디프 탭은 diff. 이미 받은
     * 파일과 diff는 다시 받지 않는다. 블록 탭 내용은 페이지와 함께 받는다.
     */
    private fun loadTab(page: String, project: String, tab: CenterTab) {
        val open = _state.value.page?.takeIf { it.detail.id == page } ?: return
        when (tab) {
            is CenterTab.Run -> loadRunEvents(page, tab.n)
            is CenterTab.File -> if (tab.path !in open.files) loadFile(page, tab.path)
            CenterTab.Diff -> if (open.diff == null) loadDiff(page, project)
            is CenterTab.Block, is CenterTab.Browser -> Unit
        }
    }

    /** 파일 탭 내용을 로컬 파일에서 읽는다. 쓰지는 않는다. */
    private fun loadFile(page: String, path: String) {
        updateOpen(page) { it.copy(files = it.files + (path to Load.Loading)) }
        scope.launch {
            val loaded = try {
                Load.Ready(files.read(path))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Load.Failed(e.message ?: e::class.simpleName)
            }
            updateOpen(page) { it.copy(files = it.files + (path to loaded)) }
        }
    }

    /**
     * 페이지 작업 폴더의 diff(`GET /projects/{p}/git/diff?page=`)를 받아 파일별로 나눈다. git
     * 저장소가 아니면(409 `no_repo`) 빈 디프로 둔다.
     */
    private fun loadDiff(page: String, project: String) {
        updateOpen(page) { it.copy(diff = it.diff.takeIf { d -> d is Load.Ready } ?: Load.Loading) }
        scope.launch {
            val loaded = try {
                val text = gitApi.getGitDiff(project, page = page).bodyOrThrow().text
                Load.Ready(DiffView(repository = true, files = parseDiff(text)))
            } catch (e: CancellationException) {
                throw e
            } catch (e: CoreApiException) {
                if (e.error?.error == NO_REPO) {
                    Load.Ready(DiffView(repository = false, files = emptyList()))
                } else {
                    Load.Failed(e.message)
                }
            } catch (e: Exception) {
                Load.Failed(e.message ?: e::class.simpleName)
            }
            updateOpen(page) { it.copy(diff = loaded) }
        }
    }

    private fun openLink(href: String, documentDir: String?) {
        when (val target = linkTarget(href, documentDir)) {
            is LinkTarget.Open -> open(target.request)
            is LinkTarget.External -> files.openExternally(target.target)
            null -> Unit
        }
    }

    /** 로컬 파일을 읽는다. 없거나 읽을 수 없으면 null. */
    private suspend fun readOrNull(path: String): String? = try {
        files.read(path)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    /** code 블록의 작업 폴더 기준 경로를 core가 알려 준 작업 폴더로 풀어 연다. */
    private fun openWorkFile(relative: String) {
        val page = _state.value.page?.detail ?: return
        request {
            val folder = gitApi.getGitStatus(page.project, page = page.id).bodyOrThrow().folder
            if (_state.value.page?.detail?.id == page.id) {
                open(OpenRequest.File(folder.trimEnd('/') + "/" + relative.trimStart('/')))
            }
        }
    }

    /** 열린 페이지가 [project]에 속하면 그 페이지에 [tab]을 연다(`runs.opened`). */
    private fun openInProject(project: String, tab: CenterTab) {
        if (_state.value.page?.detail?.project == project) openTab(tab)
    }

    /** git 상태가 바뀌었다. 열린 페이지가 그 프로젝트이고 디프를 받아 둔 적이 있으면 다시 받는다. */
    private fun reloadDiffIn(project: String) {
        val open = _state.value.page ?: return
        if (open.detail.project == project && open.diff != null) {
            loadDiff(open.detail.id, project)
        }
    }

    private fun updateDraft(page: String, block: String, change: (DataDraft) -> DataDraft) =
        updateOpen(page) { open ->
            val draft = open.drafts[block] ?: return@updateOpen open
            open.copy(drafts = open.drafts + (block to change(draft)))
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

    /** 읽지 않은 페이지를 앱 설정에 적는다. 같은 값이면 파일을 다시 쓰지 않는다. */
    private fun saveUnread(unread: Set<String>) {
        val current = settings.load()
        if (current.unread != unread) settings.save(current.copy(unread = unread))
    }

    /** 알림을 낸다. 같은 결정은 한 번만 알린다(`ask.created`와 `flow.waiting`이 함께 온다). */
    private fun notify(notice: Notice) {
        if (!settings.load().notifications) return
        val decision = notice.decision
        if (decision != null && !notifiedDecisions.add(decision)) return
        _notices.tryEmit(notice)
    }

    private fun showError(e: Exception) =
        _state.update { it.copy(loadError = e.message ?: e::class.simpleName) }

    private companion object {
        const val HTTP_BAD_REQUEST = 400
        const val NO_REPO = "no_repo"
        const val NOTICE_BUFFER = 16
    }
}
