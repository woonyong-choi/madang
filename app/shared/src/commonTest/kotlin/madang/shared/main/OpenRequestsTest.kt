package madang.shared.main

import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import madang.api.model.Block
import madang.api.model.BlockContent
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageCard
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.Project
import madang.shared.LocalFiles
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventTransport
import madang.shared.json

/** 열기 요청: 탭 종류 규칙, 파일·디프 내용, `runs.opened`, 데이터 원문 저장. */
@OptIn(ExperimentalCoroutinesApi::class)
class OpenRequestsTest {

    private val codec = CoreClient.CoreJson
    private val events = Channel<String>(Channel.UNLIMITED)
    private var repository = true
    private var diffRequests = 0
    private var diffPage: String? = null

    private val resume = PageDetail(
        id = "resume",
        project = "jobs",
        title = "이력서",
        status = PageStatus.DOING,
        pinned = false,
        tags = emptyList(),
        blocks = listOf(
            BlockHeader(id = "b01", type = BlockType.MESSAGE, text = "hi"),
            BlockHeader(id = "b02", type = BlockType.DATA, file = "blocks/b02-base.json"),
            BlockHeader(
                id = "b03",
                type = BlockType.CODE,
                file = "blocks/b03.code.yaml",
                path = "src/lock.ts"
            ),
            BlockHeader(
                id = "b04",
                type = BlockType.SITE,
                file = "blocks/b04.site.yaml",
                url = "http://localhost:5173"
            ),
            BlockHeader(id = "b05", type = BlockType.TERM, file = "blocks/b05.term.yaml")
        ),
        runs = emptyList(),
        unknownFiles = emptyList()
    )

    private val files = FakeFiles(
        mapOf(
            "/work/jobs/.github/ci.yml" to "on: push\n",
            "/work/jobs/src/lock.ts" to "export {}\n"
        )
    )

    private fun MockRequestHandleScope.handle(request: HttpRequestData) =
        when (val path = request.url.encodedPath) {
            "/projects" ->
                json(codec.encodeToString(ListSerializer(Project.serializer()), Home.projects))

            "/pages/resume" -> json(codec.encodeToString(PageDetail.serializer(), resume))

            "/pages/resume/blocks/b02" -> if (request.method == HttpMethod.Put) {
                saveBlock(request)
            } else {
                block("""{"name":"김마당"}""")
            }

            "/projects/jobs/git/status" ->
                json("""{"repository":true,"folder":"/work/jobs","files":[]}""")

            "/projects/jobs/git/diff" -> {
                diffRequests++
                diffPage = request.url.parameters["page"]
                if (repository) {
                    json(DIFF_JSON)
                } else {
                    json("""{"error":"no_repo","message":"jobs"}""", HttpStatusCode.Conflict)
                }
            }

            else -> if (path.startsWith("/projects/") && path.endsWith("/pages")) {
                json(codec.encodeToString(ListSerializer(PageCard.serializer()), emptyList()))
            } else {
                json("""{"error":"not_found","message":"$path"}""", HttpStatusCode.NotFound)
            }
        }

    private fun MockRequestHandleScope.saveBlock(request: HttpRequestData) =
        codec.decodeFromString(BlockContent.serializer(), (request.body as TextContent).text)
            .content.let { text ->
                if (text.startsWith("{") && text.endsWith("}")) {
                    block(text)
                } else {
                    json(
                        """{"error":"invalid","message":"bad json","issues":[""" +
                            """{"code":"invalid-json","message":"줄 1이 틀렸습니다","line":1}]}""",
                        HttpStatusCode.BadRequest
                    )
                }
            }

    private fun MockRequestHandleScope.block(content: String) = json(
        codec.encodeToString(Block.serializer(), Block(resume.blocks[1], content))
    )

    private fun TestScope.viewModel(): Pair<MainViewModel, MockCore> {
        val mock = MockCore(this) { handle(it) }
        val transport = EventTransport { onOpen, onFrame ->
            onOpen()
            for (frame in events) onFrame(frame)
            awaitCancellation()
        }
        val core = CoreClient("http://core", mock.engine)
        val viewModel = MainViewModel(
            core,
            EventStream(transport),
            backgroundScope,
            files = files
        )
        runCurrent()
        viewModel.openPage("resume")
        runCurrent()
        return viewModel to mock
    }

    private val MainViewModel.tabs get() = state.value.tabs

    private val MainViewModel.page get() = state.value.page!!

    private fun MainViewModel.item(key: String): FlowItem = page.flowItems.first { it.key == key }

    @Test
    fun filesOpenByTheRuleTable() = runTest {
        val (viewModel, _) = viewModel()

        viewModel.open(OpenRequest.File("/work/jobs/site/my page.html"))
        assertEquals(
            CenterTab.Browser("file:///work/jobs/site/my%20page.html"),
            viewModel.tabs.active
        )

        viewModel.open(OpenRequest.File("/work/jobs/.github/ci.yml"))
        viewModel.open(OpenRequest.File("/work/jobs/missing.ts"))
        runCurrent()
        assertEquals(CenterTab.File("/work/jobs/missing.ts"), viewModel.tabs.active)
        assertEquals(Load.Ready("on: push\n"), viewModel.page.files["/work/jobs/.github/ci.yml"])
        assertIs<Load.Failed>(viewModel.page.files["/work/jobs/missing.ts"])

        viewModel.open(OpenRequest.Terminal)
        viewModel.open(OpenRequest.Chat)
        assertEquals(3, viewModel.tabs.tabs.size)
    }

    @Test
    fun blocksOpenWhatTheyDeclare() = runTest {
        val (viewModel, _) = viewModel()

        viewModel.openItem(viewModel.item("b03"))
        runCurrent()
        assertEquals(CenterTab.File("/work/jobs/src/lock.ts"), viewModel.tabs.active)
        assertEquals(Load.Ready("export {}\n"), viewModel.page.files["/work/jobs/src/lock.ts"])

        viewModel.openItem(viewModel.item("b04"))
        assertEquals(CenterTab.Browser("http://localhost:5173"), viewModel.tabs.active)

        viewModel.openItem(viewModel.item("b05"))
        viewModel.openItem(viewModel.item("b01"))
        assertEquals(2, viewModel.tabs.tabs.size)
    }

    @Test
    fun runsOpenedOpensABrowserTabOnlyForTheOpenProject() = runTest {
        val (viewModel, _) = viewModel()

        events.send(runsOpened("blog", "http://localhost:4000"))
        runCurrent()
        assertEquals(TabSet(), viewModel.tabs)

        events.send(runsOpened("jobs", "http://localhost:5173"))
        runCurrent()
        assertEquals(CenterTab.Browser("http://localhost:5173"), viewModel.tabs.active)
    }

    @Test
    fun diffTabSplitsCoreDiffByFileAndReloadsOnGitChange() = runTest {
        val (viewModel, _) = viewModel()

        viewModel.open(OpenRequest.Diff)
        runCurrent()
        assertEquals(CenterTab.Diff, viewModel.tabs.active)
        val view = assertIs<Load.Ready<DiffView>>(viewModel.page.diff).value
        assertTrue(view.repository)
        assertEquals(listOf("src/lock.ts"), view.files.map { it.path })
        assertEquals("resume", diffPage)

        repository = false
        events.send(
            """{"type":"git.changed","ts":"t","project":"jobs",""" +
                """"data":{"folder":"/work/jobs","action":"commit"}}"""
        )
        runCurrent()
        assertEquals(2, diffRequests)
        assertEquals(Load.Ready(DiffView(false, emptyList())), viewModel.page.diff)
    }

    @Test
    fun dataSourceIsSavedThroughCoreAndRejectionsStayOnTheLine() = runTest {
        val (viewModel, mock) = viewModel()
        viewModel.openItem(viewModel.item("b02"))

        viewModel.editData("b02", "name: 김마당")
        viewModel.saveData("b02")
        runCurrent()
        val rejected = viewModel.page.drafts.getValue("b02")
        assertEquals(listOf(1), rejected.issuesByLine.keys.toList())
        assertEquals("""{"name":"김마당"}""", viewModel.page.contents["b02"])

        viewModel.editData("b02", """{"name":"김마당","title":"엔지니어"}""")
        viewModel.saveData("b02")
        runCurrent()
        assertNull(viewModel.page.drafts["b02"])
        assertEquals("""{"name":"김마당","title":"엔지니어"}""", viewModel.page.contents["b02"])
        assertEquals(2, mock.requests.count { it.first == "PUT /pages/resume/blocks/b02" })

        viewModel.editData("b02", "x")
        viewModel.discardData("b02")
        assertNull(viewModel.page.drafts["b02"])
    }

    @Test
    fun externalOpenGoesToThePlatform() = runTest {
        val (viewModel, _) = viewModel()

        viewModel.openExternally("/work/jobs/src/lock.ts")

        assertEquals(listOf("/work/jobs/src/lock.ts"), files.opened)
    }

    private fun runsOpened(project: String, url: String) =
        """{"type":"runs.opened","ts":"t","project":"$project",""" +
            """"data":{"name":"사이트","url":"$url"}}"""

    /** 메모리에 든 파일만 읽는 [LocalFiles]. */
    private class FakeFiles(private val contents: Map<String, String>) : LocalFiles {
        val opened = mutableListOf<String>()

        override suspend fun read(path: String): String =
            contents[path] ?: throw IllegalStateException("no such file: $path")

        override fun openExternally(target: String) {
            opened += target
        }
    }

    private companion object {
        val DIFF_JSON = JsonObject(
            mapOf(
                "text" to JsonPrimitive(
                    "diff --git a/src/lock.ts b/src/lock.ts\nnew file mode 100644\n" +
                        "--- /dev/null\n+++ b/src/lock.ts\n@@ -0,0 +1 @@\n+export {}\n"
                )
            )
        ).toString()
    }
}
