package madang.shared.main

import kotlin.time.TimeSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.BlocksApi
import madang.api.client.PagesApi
import madang.api.client.RunsApi
import madang.api.client.SpacesApi
import madang.api.model.BlockAddedEvent
import madang.api.model.BlockDeletedEvent
import madang.api.model.BlockType
import madang.api.model.BlockUpdatedEvent
import madang.api.model.PageCard
import madang.api.model.PageCreate
import madang.api.model.PageCreatedEvent
import madang.api.model.PageDeletedEvent
import madang.api.model.PageUpdate
import madang.api.model.PageUpdatedEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.Space
import madang.api.model.SpaceCreate
import madang.api.model.SpaceCreatedEvent
import madang.api.model.SpaceDeletedEvent
import madang.api.model.SpaceSort
import madang.api.model.SpaceUpdate
import madang.api.model.SpaceUpdatedEvent
import madang.shared.core.CoreClient
import madang.shared.core.CoreEvent
import madang.shared.core.EventStream
import madang.shared.core.EventStreamItem
import madang.shared.core.bodyOrThrow

/**
 * 레이어 0(공간 / 페이지 목록 / 페이지 본문).
 *
 * 연결이 열릴 때마다 공간과 모든 페이지 카드를 다시 받고, 이후에는 이벤트로 고친다.
 * 사용자 조작은 core에 요청하고 core의 응답(수정된 공간·카드)으로 상태를 고친다.
 *
 * @param newPageTitle 새 페이지의 처음 제목.
 */
class MainViewModel(
    private val core: CoreClient,
    events: EventStream,
    private val scope: CoroutineScope,
    private val newPageTitle: String = "Untitled",
    private val timeSource: TimeSource = TimeSource.Monotonic
) {
    private val _state = MutableStateFlow(MainState(baseUrl = core.baseUrl))
    val state: StateFlow<MainState> = _state.asStateFlow()

    private val spacesApi = core.api(::SpacesApi)
    private val pagesApi = core.api(::PagesApi)
    private val blocksApi = core.api(::BlocksApi)
    private val runsApi = core.api(::RunsApi)

    init {
        scope.launch { events.items().collect(::onItem) }
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
        it.copy(source = source, pane = if (advance) Pane.LIST else Pane.SPACES)
    }

    fun toggleSpace(slug: String) = _state.update {
        val open = it.expandedSpaces
        it.copy(expandedSpaces = if (slug in open) open - slug else open + slug)
    }

    fun toggleTag(path: String) = _state.update {
        val open = it.expandedTags
        it.copy(expandedTags = if (path in open) open - path else open + path)
    }

    /** 공간 포커스. null이면 해제한다. */
    fun focusOn(slug: String?) = _state.update {
        it.copy(
            focusSpace = slug,
            source = slug?.let(ListSource::InSpace) ?: it.source,
            expandedSpaces = slug?.let { s -> it.expandedSpaces + s } ?: it.expandedSpaces
        )
    }

    fun setFilter(filter: PageFilter) = _state.update { it.copy(filter = filter) }

    /** 고른 공간의 정렬을 바꾼다. 태그를 보고 있으면 바꿀 공간이 없다. */
    fun setSort(sort: SpaceSort) {
        val slug = (_state.value.source as? ListSource.InSpace)?.slug ?: return
        request { upsertSpace(spacesApi.updateSpace(slug, SpaceUpdate(sort = sort)).bodyOrThrow()) }
    }

    /** 페이지를 고르고 연다. [advance]면 본문 열로 넘어간다(열이 모자랄 때). */
    fun openPage(id: String, advance: Boolean = false) {
        _state.update { it.copy(selectedPage = id, pane = if (advance) Pane.PAGE else Pane.LIST) }
        loadPage(id)
    }

    fun toggleExpandAll() = _state.update {
        it.copy(expandAll = !it.expandAll, toggled = emptySet())
    }

    fun toggleFold(key: String) = _state.update {
        it.copy(toggled = if (key in it.toggled) it.toggled - key else it.toggled + key)
    }

    fun newPage() {
        val space = _state.value.targetSpace
        request {
            val created = pagesApi.createPage(space, PageCreate(title = newPageTitle)).bodyOrThrow()
            val cards = pagesApi.listPages(space).bodyOrThrow()
            _state.update { state ->
                state.copy(
                    cards = state.cards.filter { it.space != space } + cards,
                    source = state.source as? ListSource.InSpace ?: ListSource.InSpace(space),
                    selectedPage = created.id,
                    page = OpenPage(created),
                    pane = Pane.PAGE
                )
            }
        }
    }

    /** 최상위 공간을 만든다. slug는 제목에서 만든다. */
    fun createSpace(title: String) {
        val taken = _state.value.spaces.mapTo(mutableSetOf()) { it.slug }
        request {
            val space = spacesApi.createSpace(
                SpaceCreate(slug = slugFor(title, taken), title = title)
            )
                .bodyOrThrow()
            upsertSpace(space)
            _state.update { it.copy(source = ListSource.InSpace(space.slug)) }
        }
    }

    fun renameSpace(slug: String, title: String) = updateSpace(slug, SpaceUpdate(title = title))

    fun linkRepo(slug: String, path: String) = updateSpace(slug, SpaceUpdate(repo = path))

    fun deleteSpace(slug: String) = request {
        spacesApi.deleteSpace(slug).bodyOrThrow()
        removeSpace(slug)
    }

    fun setPinned(id: String, pinned: Boolean) = updatePage(id, PageUpdate(pinned = pinned))

    fun setTags(id: String, tags: List<String>) = updatePage(id, PageUpdate(tags = tags.distinct()))

    /** 페이지에 태그 하나를 더한다(태그로 끌어다 놓기). */
    fun addTag(id: String, tag: String) {
        val card = _state.value.cards.firstOrNull { it.id == id } ?: return
        if (tag !in card.tags) setTags(id, card.tags + tag)
    }

    fun movePage(id: String, space: String) {
        val card = _state.value.cards.firstOrNull { it.id == id } ?: return
        if (card.space != space) updatePage(id, PageUpdate(space = space))
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
            is SpaceCreatedEvent -> upsertSpace(payload.data.space)

            is SpaceUpdatedEvent -> upsertSpace(payload.data.space)

            is SpaceDeletedEvent -> removeSpace(payload.data.id)

            is PageCreatedEvent -> upsertCard(payload.data.page)

            is PageUpdatedEvent -> upsertCard(payload.data.page).also {
                refreshIfOpen(payload.page)
            }

            is PageDeletedEvent -> removeCard(payload.data.id)

            is BlockAddedEvent, is BlockUpdatedEvent, is BlockDeletedEvent,
            is RunFinishedEvent, is RunFailedEvent -> refreshIfOpen(event.envelope.page)
        }
    }

    private fun reloadAll() = request {
        val spaces = spacesApi.listSpaces().bodyOrThrow()
        val cards = spaces.flatMap { pagesApi.listPages(it.slug).bodyOrThrow() }
        _state.update { it.withLoaded(spaces, cards) }
        _state.value.selectedPage?.let(::loadPage)
    }

    private fun refreshIfOpen(page: String?) {
        if (page != null && _state.value.page?.detail?.id == page) loadPage(page)
    }

    /** 페이지와 doc·data 블록 내용을 불러온다. 그사이 다른 페이지를 골랐으면 버린다. */
    private fun loadPage(id: String) = request {
        val detail = pagesApi.getPage(id).bodyOrThrow()
        if (_state.value.selectedPage != id) return@request
        _state.update { state ->
            val kept = state.page?.takeIf { it.detail.id == id }?.contents.orEmpty()
            val toggled = if (state.page?.detail?.id == id) state.toggled else emptySet()
            state.copy(page = OpenPage(detail, kept), toggled = toggled)
        }
        val contents = detail.blocks
            .filter { it.type == BlockType.DOC || it.type == BlockType.DATA }
            .associate { it.id to blocksApi.getBlock(id, it.id).bodyOrThrow().content }
        _state.update { state ->
            val open = state.page?.takeIf { it.detail.id == id } ?: return@update state
            state.copy(page = open.copy(contents = contents))
        }
    }

    private fun updateSpace(slug: String, update: SpaceUpdate) = request {
        upsertSpace(spacesApi.updateSpace(slug, update).bodyOrThrow())
    }

    private fun updatePage(id: String, update: PageUpdate) = request {
        upsertCard(pagesApi.updatePage(id, update).bodyOrThrow())
    }

    private fun upsertSpace(space: Space) = _state.update { state ->
        val others = state.spaces.filter { it.slug != space.slug }
        state.copy(spaces = others + space)
    }

    private fun removeSpace(slug: String) = _state.update { state ->
        state.withLoaded(state.spaces.filter { it.slug != slug }, state.cards)
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

    private fun removeCard(id: String) = _state.update { state ->
        val closing = state.selectedPage == id
        state.copy(
            cards = state.cards.filter { it.id != id },
            selectedPage = state.selectedPage.takeUnless { closing },
            page = state.page.takeUnless { closing },
            pane = if (closing && state.pane == Pane.PAGE) Pane.LIST else state.pane
        )
    }

    /** core 요청을 띄운다. 실패하면 상태 줄에 원인을 보인다. */
    private fun request(block: suspend () -> Unit) {
        scope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(loadError = e.message ?: e::class.simpleName) }
            }
        }
    }
}
