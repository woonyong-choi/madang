package madang.shared.main

import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import madang.api.model.Block
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.Space
import madang.api.model.SpaceSort
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventTransport
import madang.shared.json

/** ViewModel은 backgroundScope에서 돈다. 배경 작업까지 돌리려면 runCurrent를 쓴다. */
@OptIn(ExperimentalCoroutinesApi::class)
class MainViewModelTest {

    private val codec = CoreClient.CoreJson

    private val resumeDetail = PageDetail(
        id = "resume",
        space = "jobs",
        title = "이력서",
        status = Home.resume.status,
        pinned = true,
        tags = listOf("이력서"),
        blocks = listOf(
            BlockHeader(id = "b01", type = BlockType.MESSAGE, text = "hi"),
            BlockHeader(id = "b02", type = BlockType.DOC, file = "blocks/b02-notes.md")
        ),
        runs = emptyList(),
        unknownFiles = emptyList()
    )

    private fun TestScope.fixture(
        events: Channel<String> = Channel(Channel.UNLIMITED)
    ): Pair<MainViewModel, MockCore> {
        val mock = MockCore(this) { request ->
            val path = request.url.encodedPath
            when {
                path == "/spaces" ->
                    json(codec.encodeToString(ListSerializer(Space.serializer()), Home.spaces))

                path.startsWith("/spaces/") && path.endsWith("/pages") -> {
                    val slug = path.removePrefix("/spaces/").removeSuffix("/pages")
                    val cards = Home.cards.filter { it.space == slug }
                    json(codec.encodeToString(ListSerializer(PageCard.serializer()), cards))
                }

                path == "/spaces/jobs" && request.method == HttpMethod.Patch -> json(
                    codec.encodeToString(
                        Space.serializer(),
                        Home.spaces[1].copy(sort = SpaceSort.TITLE)
                    )
                )

                path == "/pages/posting" && request.method == HttpMethod.Patch -> json(
                    codec.encodeToString(PageCard.serializer(), Home.posting.copy(pinned = true))
                )

                path == "/pages/resume" -> json(
                    codec.encodeToString(PageDetail.serializer(), resumeDetail)
                )

                path == "/pages/resume/blocks/b02" -> json(
                    codec.encodeToString(
                        Block.serializer(),
                        Block(resumeDetail.blocks[1], "# 메모")
                    )
                )

                else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
            }
        }
        val transport = EventTransport { onOpen, onFrame ->
            onOpen()
            for (frame in events) onFrame(frame)
            awaitCancellation()
        }
        val core = CoreClient("http://core", mock.engine)
        return MainViewModel(core, EventStream(transport), backgroundScope, "제목 없음") to mock
    }

    @Test
    fun resyncLoadsSpacesAndEveryPage() = runTest {
        val (viewModel, _) = fixture()

        runCurrent()

        val state = viewModel.state.value
        assertEquals(EventLink.Live, state.link)
        assertEquals(Home.spaces.map { it.slug }.toSet(), state.spaces.map { it.slug }.toSet())
        assertEquals(Home.cards.map { it.id }.toSet(), state.cards.map { it.id }.toSet())
        assertEquals(ListSource.InSpace(ROOT_SPACE), state.source)
    }

    @Test
    fun keyboardOpensPageAndLoadsDocContent() = runTest {
        val (viewModel, _) = fixture()
        runCurrent()

        viewModel.select(ListSource.InSpace("jobs"))
        viewModel.onKey(NavKey.ENTER)
        runCurrent()

        val state = viewModel.state.value
        assertEquals(Pane.LIST, state.pane)
        assertEquals("resume", state.page?.detail?.id)
        assertEquals(mapOf("b02" to "# 메모"), state.page?.contents)

        viewModel.onKey(NavKey.RIGHT)
        assertEquals(Pane.PAGE, viewModel.state.value.pane)
    }

    @Test
    fun sortAndPinGoToCoreAndApplyTheResponse() = runTest {
        val (viewModel, mock) = fixture()
        runCurrent()
        viewModel.select(ListSource.InSpace("jobs"))

        viewModel.setSort(SpaceSort.TITLE)
        viewModel.setPinned("posting", true)
        runCurrent()

        assertTrue("PATCH /spaces/jobs" to """{"sort":"title"}""" in mock.requests)
        assertTrue("PATCH /pages/posting" to """{"pinned":true}""" in mock.requests)
        val state = viewModel.state.value
        assertEquals(listOf("posting", "resume", "cover"), state.listCards.map { it.id })
    }

    @Test
    fun pageEventsUpdateCards() = runTest {
        val events = Channel<String>(Channel.UNLIMITED)
        val (viewModel, _) = fixture(events)
        runCurrent()

        val updated = codec.encodeToString(PageCard.serializer(), Home.draft.copy(title = "GC 정리"))
        events.send(
            """{"type":"page.updated","ts":"t","space":"blog","page":"draft","data":{"page":$updated}}"""
        )
        events.send(
            """{"type":"page.deleted","ts":"t","space":"jobs","page":"cover","data":{"id":"cover"}}"""
        )
        runCurrent()

        val cards = viewModel.state.value.cards
        assertEquals("GC 정리", cards.first { it.id == "draft" }.title)
        assertTrue(cards.none { it.id == "cover" })
    }
}
