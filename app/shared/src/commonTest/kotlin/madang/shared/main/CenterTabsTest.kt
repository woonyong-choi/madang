package madang.shared.main

import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import madang.api.model.Block
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.RunRecord
import madang.api.model.RunUsage
import madang.api.model.RunVerify
import madang.api.model.Space
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventTransport
import madang.shared.json
import madang.shared.settings.InMemorySettingsStore

/** 가운데 열 탭: 열기, 중복 방지, 닫기, 페이지별 기억, 입력창 대상 전환. */
@OptIn(ExperimentalCoroutinesApi::class)
class CenterTabsTest {

    private val codec = CoreClient.CoreJson
    private val events = Channel<String>(Channel.UNLIMITED)
    private val settings = InMemorySettingsStore()

    private val resume = PageDetail(
        id = "resume",
        space = "jobs",
        title = "이력서",
        status = PageStatus.DOING,
        pinned = true,
        tags = emptyList(),
        blocks = listOf(
            BlockHeader(id = "b01", type = BlockType.MESSAGE, text = "hi"),
            BlockHeader(id = "b02", type = BlockType.DOC, file = "blocks/b02-notes.md"),
            BlockHeader(id = "b03", type = BlockType.DATA, title = "base.json"),
            BlockHeader(id = "b04", type = BlockType.VIEW, title = "이력서")
        ),
        runs = listOf(
            RunRecord(
                n = 1,
                usage = RunUsage(input = 29104, cached = 24310, output = 612),
                changedFiles = listOf("blocks/b03-base.json"),
                unknownFiles = emptyList(),
                verify = RunVerify()
            )
        ),
        unknownFiles = emptyList()
    )

    private val cover = resume.copy(
        id = "cover",
        space = "jobs-2026",
        title = "자기소개서",
        blocks = listOf(BlockHeader(id = "b01", type = BlockType.DOC, file = "blocks/b01.md")),
        runs = emptyList()
    )

    private val previews = mutableListOf<String?>()

    private fun TestScope.viewModel(): Pair<MainViewModel, MockCore> {
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

                path == "/pages/resume" -> json(
                    codec.encodeToString(PageDetail.serializer(), resume)
                )

                path == "/pages/cover" -> json(codec.encodeToString(PageDetail.serializer(), cover))

                path.matches(Regex("/pages/\\w+/blocks/\\w+")) -> {
                    val header =
                        BlockHeader(id = path.substringAfterLast('/'), type = BlockType.DOC)
                    json(codec.encodeToString(Block.serializer(), Block(header, "[1, 2]")))
                }

                path == "/pages/resume/runs/1/events" ->
                    json("""[{"type":"text","text":"찾는 중"},{"type":"done","text":"끝"}]""")

                path.endsWith("/preview-input") -> {
                    previews += request.url.parameters["target"]
                    json(PREVIEW_JSON)
                }

                path == "/pages/resume/messages" && request.method == HttpMethod.Post ->
                    json("""{"message":"b09"}""", HttpStatusCode.Accepted)

                else -> json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
            }
        }
        val transport = EventTransport { onOpen, onFrame ->
            onOpen()
            for (frame in events) onFrame(frame)
            awaitCancellation()
        }
        val core = CoreClient("http://core", mock.engine)
        val viewModel =
            MainViewModel(core, EventStream(transport), backgroundScope, "제목 없음", settings)
        runCurrent()
        return viewModel to mock
    }

    private fun TestScope.open(viewModel: MainViewModel, page: String) {
        viewModel.openPage(page)
        runCurrent()
    }

    private fun MainViewModel.item(key: String): FlowItem =
        state.value.page!!.flowItems.first { it.key == key }

    @Test
    fun clickingDocDataAndRunOpensOneTabEach() = runTest {
        val (viewModel, _) = viewModel()
        open(viewModel, "resume")

        viewModel.openItem(viewModel.item("b02"))
        viewModel.openItem(viewModel.item("b04"))
        viewModel.openItem(viewModel.item("b01"))
        viewModel.openItem(viewModel.item("run-1"))
        viewModel.openItem(viewModel.item("b02"))
        runCurrent()

        val state = viewModel.state.value
        assertEquals(listOf(BlockTab.Block("b02"), BlockTab.Run(1)), state.tabs.tabs)
        assertEquals(BlockTab.Block("b02"), state.tabs.active)
        assertEquals(listOf("text", "done"), state.page?.runEvents?.get(1)?.map { it.type.value })
    }

    @Test
    fun tabKeysCloseAndCycleButKeepThePageTab() = runTest {
        val (viewModel, _) = viewModel()
        open(viewModel, "resume")
        viewModel.openTab(BlockTab.Block("b02"))
        viewModel.openTab(BlockTab.Block("b03"))

        viewModel.onTabKey(TabKey.NEXT)
        assertNull(viewModel.state.value.tabs.active)
        viewModel.onTabKey(TabKey.CLOSE)
        assertEquals(2, viewModel.state.value.tabs.tabs.size)

        viewModel.onTabKey(TabKey.PREVIOUS)
        assertEquals(BlockTab.Block("b03"), viewModel.state.value.tabs.active)
        viewModel.onTabKey(TabKey.CLOSE)
        assertEquals(
            TabSet(listOf(BlockTab.Block("b02")), BlockTab.Block("b02")),
            viewModel.state.value.tabs
        )

        viewModel.onTabKey(TabKey.PAGE)
        assertNull(viewModel.state.value.tabs.active)
        viewModel.closeTab(BlockTab.Block("b02"))
        assertEquals(TabSet(), viewModel.state.value.tabs)
    }

    @Test
    fun eachPageKeepsItsOwnTabSetAcrossRestarts() = runTest {
        val (viewModel, _) = viewModel()
        open(viewModel, "resume")
        viewModel.openTab(BlockTab.Block("b03"))
        viewModel.openTab(BlockTab.Run(1))

        open(viewModel, "cover")
        assertEquals(TabSet(), viewModel.state.value.tabs)
        viewModel.openTab(BlockTab.Block("b01"))

        open(viewModel, "resume")
        val restored = TabSet(listOf(BlockTab.Block("b03"), BlockTab.Run(1)), BlockTab.Run(1))
        assertEquals(restored, viewModel.state.value.tabs)
        assertEquals(setOf("resume", "cover"), settings.load().pageTabs.keys)

        val (restarted, _) = viewModel()
        open(restarted, "resume")
        assertEquals(restored, restarted.state.value.tabs)
        open(restarted, "cover")
        assertEquals(BlockTab.Block("b01"), restarted.state.value.tabs.active)
    }

    @Test
    fun deletedPageForgetsItsTabs() = runTest {
        val (viewModel, _) = viewModel()
        open(viewModel, "resume")
        viewModel.openTab(BlockTab.Block("b02"))

        events.send(
            """{"type":"page.deleted","ts":"t","space":"jobs","page":"resume","data":{"id":"resume"}}"""
        )
        runCurrent()

        assertEquals(TabSet(), viewModel.state.value.tabs)
        assertTrue(settings.load().pageTabs.isEmpty())
    }

    @Test
    fun composerTargetsTheActiveTab() = runTest {
        val (viewModel, mock) = viewModel()
        open(viewModel, "resume")
        assertEquals(SendTarget("resume"), viewModel.composer.state.value.target)

        viewModel.composer.setText("표를 정리해줘")
        viewModel.openTab(BlockTab.Block("b03"))
        runCurrent()
        val onData = viewModel.composer.state.value
        assertEquals(SendTarget("resume", "b03", "base.json"), onData.target)
        assertEquals("표를 정리해줘", onData.text)

        advanceTimeBy(ComposerViewModel.PREVIEW_DEBOUNCE.inWholeMilliseconds + 1)
        runCurrent()
        assertEquals("b03", previews.last())

        viewModel.send()
        runCurrent()
        val body = mock.requests.last { it.first == "POST /pages/resume/messages" }.second
        assertEquals("""{"text":"표를 정리해줘","target":{"block":"b03"}}""", body)

        viewModel.openTab(BlockTab.Run(1))
        runCurrent()
        assertEquals(SendTarget("resume"), viewModel.composer.state.value.target)
        viewModel.onTabKey(TabKey.PAGE)
        runCurrent()
        assertEquals(SendTarget("resume"), viewModel.composer.state.value.target)
    }

    private companion object {
        const val PREVIEW_JSON =
            """{"kind":"small","tier":1,"runner":"codex","model":"gpt-6-luna",""" +
                """"parts":{"system_est":1,"root":1,"space":1,"state":1,"contract":1,""" +
                """"target":1,"request":1},"total_est":7}"""
    }
}
