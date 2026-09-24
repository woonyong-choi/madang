package madang.shared.main

import io.ktor.client.engine.mock.respond
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
import madang.api.model.Project
import madang.api.model.ProjectSort
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
        project = "jobs",
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
                path == "/projects" && request.method == HttpMethod.Post -> json(
                    codec.encodeToString(Project.serializer(), project("site")),
                    HttpStatusCode.Created
                )

                path == "/projects" ->
                    json(codec.encodeToString(ListSerializer(Project.serializer()), Home.projects))

                path == "/projects/blog" && request.method == HttpMethod.Delete ->
                    respond("", HttpStatusCode.NoContent)

                path.startsWith("/projects/") && path.endsWith("/pages") -> {
                    val id = path.removePrefix("/projects/").removeSuffix("/pages")
                    val cards = Home.cards.filter { it.project == id }
                    json(codec.encodeToString(ListSerializer(PageCard.serializer()), cards))
                }

                path == "/projects/jobs" && request.method == HttpMethod.Patch -> json(
                    codec.encodeToString(
                        Project.serializer(),
                        Home.projects[1].copy(sort = ProjectSort.TITLE)
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
    fun resyncLoadsProjectsAndEveryPage() = runTest {
        val (viewModel, _) = fixture()

        runCurrent()

        val state = viewModel.state.value
        assertEquals(EventLink.Live, state.link)
        assertEquals(Home.projects.map { it.id }.toSet(), state.projects.map { it.id }.toSet())
        assertEquals(Home.cards.map { it.id }.toSet(), state.cards.map { it.id }.toSet())
        assertEquals(ListSource.InProject(NOTES), state.source)
    }

    @Test
    fun keyboardOpensPageAndLoadsDocContent() = runTest {
        val (viewModel, _) = fixture()
        runCurrent()

        viewModel.select(ListSource.InProject("jobs"))
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
        viewModel.select(ListSource.InProject("jobs"))

        viewModel.setSort(ProjectSort.TITLE)
        viewModel.setPinned("posting", true)
        runCurrent()

        assertTrue("PATCH /projects/jobs" to """{"sort":"title"}""" in mock.requests)
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
            """{"type":"page.updated","ts":"t","project":"blog","page":"draft","data":{"page":$updated}}"""
        )
        events.send(
            """{"type":"page.deleted","ts":"t","project":"jobs","page":"cover","data":{"id":"cover"}}"""
        )
        runCurrent()

        val cards = viewModel.state.value.cards
        assertEquals("GC 정리", cards.first { it.id == "draft" }.title)
        assertTrue(cards.none { it.id == "cover" })
    }

    @Test
    fun addedFolderBecomesSelectedProjectOnceEvenWithItsEvent() = runTest {
        val events = Channel<String>(Channel.UNLIMITED)
        val (viewModel, mock) = fixture(events)
        runCurrent()

        viewModel.addProject("/work/site")
        runCurrent()
        val created = codec.encodeToString(Project.serializer(), project("site"))
        events.send(
            """{"type":"project.created","ts":"t","project":"site","data":{"project":$created}}"""
        )
        runCurrent()

        assertTrue("POST /projects" to """{"path":"/work/site"}""" in mock.requests)
        val state = viewModel.state.value
        assertEquals(1, state.projects.count { it.id == "site" })
        assertEquals(ListSource.InProject("site"), state.source)
        assertEquals("site", state.targetProject)
    }

    @Test
    fun removedProjectDropsItsCardsAndSelection() = runTest {
        val (viewModel, mock) = fixture()
        runCurrent()
        viewModel.select(ListSource.InProject("blog"))

        viewModel.removeProject("blog")
        runCurrent()

        assertTrue("DELETE /projects/blog" to null in mock.requests)
        val state = viewModel.state.value
        assertTrue(state.projects.none { it.id == "blog" })
        assertTrue(state.cards.none { it.project == "blog" })
        assertEquals(ListSource.InProject(NOTES), state.source)
    }

    @Test
    fun newPageNeedsAProject() = runTest {
        val empty = MainState(baseUrl = "http://core").withLoaded(emptyList(), emptyList())

        assertEquals(null, empty.targetProject)
        assertEquals(null, empty.source)
    }
}
