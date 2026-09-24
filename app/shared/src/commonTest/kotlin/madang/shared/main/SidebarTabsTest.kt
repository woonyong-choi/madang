package madang.shared.main

import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import madang.api.client.FilesApi
import madang.api.client.GitApi
import madang.api.client.RunnersApi
import madang.api.client.RunsApi
import madang.api.model.FileEntry
import madang.api.model.FileLens
import madang.api.model.GitFile
import madang.api.model.InputParts
import madang.api.model.RunInput
import madang.api.model.RunProgressEvent
import madang.api.model.RunStreamEvent
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.json

/** 파일 렌즈, git 탭의 비git 분기, 지금 탭의 로그·입력 구성, 포트 선언. */
@OptIn(ExperimentalCoroutinesApi::class)
class SidebarTabsTest {

    /** 경로("GET /projects/p/files")별 응답 본문과 상태. 없으면 404. */
    private val routes = mutableMapOf<String, Pair<String, HttpStatusCode>>()

    private fun TestScope.core(): Pair<CoreClient, MockCore> {
        val mock = MockCore(this) { request -> respond(request) }
        return CoreClient("http://core", mock.engine) to mock
    }

    private fun MockRequestHandleScope.respond(request: HttpRequestData): HttpResponseData {
        val key = "${request.method.value} ${request.url.encodedPath}"
        val (body, status) = routes[key]
            ?: ("""{"error":"not_found","message":"$key"}""" to HttpStatusCode.NotFound)
        return json(body, status)
    }

    private fun MockCore.queries(path: String): List<String> =
        engine.requestHistory.filter { it.url.encodedPath == path }.map { it.url.encodedQuery }

    @Test
    fun madangFolderStartsFoldedAndOtherFoldersOpen() {
        val entries = listOf(
            FileEntry(".madang", FileEntry.Type.DIR),
            FileEntry(".madang/brief.md", FileEntry.Type.FILE),
            FileEntry("site", FileEntry.Type.DIR, runs = listOf("사이트")),
            FileEntry("site/index.html", FileEntry.Type.FILE)
        )

        val rows = fileRows(entries, toggled = emptySet())
        assertEquals(listOf(".madang", "site", "site/index.html"), rows.map { it.path })
        assertEquals(listOf("사이트"), rows[1].runs)
        assertEquals(emptyList(), rows[0].runs)

        val toggled = fileRows(entries, toggled = setOf(".madang", "site"))
        assertEquals(listOf(".madang", ".madang/brief.md", "site"), toggled.map { it.path })
    }

    @Test
    fun changedLensFilesGetTheirFoldersBack() {
        val rows = fileRows(
            listOf(FileEntry("src/session/lock.ts", FileEntry.Type.FILE, change = " M")),
            emptySet()
        )

        assertEquals(listOf("src", "src/session", "src/session/lock.ts"), rows.map { it.path })
        assertEquals(listOf(0, 1, 2), rows.map { it.depth })
        assertEquals(" M", rows.last().change)
    }

    @Test
    fun lensIsSentToCoreAndChangedLensKnowsANonRepository() = runTest {
        routes["GET /projects/p/files"] = TREE_JSON to HttpStatusCode.OK
        val (client, mock) = core()
        val files = FilesViewModel(client.api(::FilesApi), client.api(::RunsApi), backgroundScope)

        files.open("p", page = null)
        runCurrent()
        assertEquals(listOf(FileLens.ALL, FileLens.CHANGED), files.state.value.lenses)
        assertEquals("/root/.madang", files.state.value.absolutePath(files.state.value.rows[0]))

        files.setLens(FileLens.PAGE)
        assertEquals(FileLens.ALL, files.state.value.lens)

        routes["GET /projects/p/files"] = NO_REPO_JSON to HttpStatusCode.Conflict
        files.setLens(FileLens.CHANGED)
        runCurrent()
        assertTrue(files.state.value.noRepository)
        assertNull(files.state.value.tree)
        assertEquals(listOf("lens=all", "lens=changed"), mock.queries("/projects/p/files"))

        files.open("p", page = "pg")
        files.setLens(FileLens.PAGE)
        runCurrent()
        assertEquals("lens=page&page=pg", mock.queries("/projects/p/files").last())
    }

    @Test
    fun nonRepositoryOnlyAsksStatusAndOffersGitInit() = runTest {
        routes["GET /projects/p/git/status"] = STATUS_NO_REPO to HttpStatusCode.OK
        routes["POST /projects/p/git/init"] = STATUS_NO_REPO to HttpStatusCode.Created
        val (client, mock) = core()
        val git = GitViewModel(client.api(::GitApi), backgroundScope)

        git.open("p", page = null)
        runCurrent()
        val view = assertIs<Load.Ready<GitView>>(git.state.value.view).value
        assertFalse(view.repository)
        assertEquals(listOf("GET /projects/p/git/status"), mock.requests.map { it.first })

        git.init()
        runCurrent()
        assertEquals("POST /projects/p/git/init", mock.requests[1].first)
        assertEquals("GET /projects/p/git/status", mock.requests.last().first)
    }

    @Test
    fun repositoryLoadsBranchesWorktreesAndLogAndCommitsThroughCore() = runTest {
        routes["GET /projects/p/git/status"] = STATUS_REPO to HttpStatusCode.OK
        routes["GET /projects/p/git/branches"] = """{"current":"main","branches":["main"]}""" to
            HttpStatusCode.OK
        routes["GET /projects/p/git/worktrees"] = WORKTREES_JSON to HttpStatusCode.OK
        routes["GET /projects/p/git/log"] = "[]" to HttpStatusCode.OK
        routes["POST /projects/p/git/stage"] = STATUS_REPO to HttpStatusCode.OK
        routes["POST /projects/p/git/commit"] = """{"commit":"abc"}""" to HttpStatusCode.OK
        val (client, mock) = core()
        val git = GitViewModel(client.api(::GitApi), backgroundScope)

        git.open("p", page = "pg")
        runCurrent()
        val view = assertIs<Load.Ready<GitView>>(git.state.value.view).value
        assertEquals("pg", view.worktrees.last().page)
        assertEquals(listOf("page=pg&ref=HEAD&limit=20"), mock.queries("/projects/p/git/log"))

        git.stage(listOf("a.txt"))
        runCurrent()
        git.setMessage("feat: add a")
        git.commit()
        runCurrent()
        val bodies = mock.requests.filter { it.first.startsWith("POST") }.map { it.second }
        assertEquals(listOf("""{"paths":["a.txt"]}""", """{"message":"feat: add a"}"""), bodies)
        assertEquals("", git.state.value.message)
    }

    @Test
    fun stagedAndUnstagedFollowPorcelainCodes() {
        assertTrue(GitFile("a", "M ").staged)
        assertFalse(GitFile("a", "M ").unstaged)
        assertTrue(GitFile("a", " M").unstaged)
        assertTrue(GitFile("a", "MM").staged && GitFile("a", "MM").unstaged)
        assertFalse(GitFile("a", "??").staged)
        assertTrue(GitFile("a", "??").unstaged)
    }

    @Test
    fun logKeepsTheLastThirtyLinesAndFollowsProgress() = runTest {
        val lines = (1..40).joinToString(",") { """{"type":"text","text":"line $it"}""" }
        routes["GET /pages/pg/runs/2/events"] = "[$lines]" to HttpStatusCode.OK
        val (client, _) = core()
        val now = NowViewModel(client.api(::RunsApi), client.api(::RunnersApi), backgroundScope)
        val item = NowItem("p", "pg", "페이지", 2, null, null, RunGlyph.RUNNING, null, false)

        now.toggleLog(item)
        runCurrent()
        val log = assertIs<Load.Ready<List<RunStreamEvent>>>(now.state.value.log?.second).value
        assertEquals(NOW_LOG_LINES, log.size)
        assertEquals("line 11", log.first().text)

        now.onProgress(
            RunProgressEvent(
                type = RunProgressEvent.Type.RUN_PERIOD_PROGRESS,
                ts = "t",
                project = "p",
                page = "pg",
                run = 2,
                data = RunStreamEvent(type = RunStreamEvent.Type.TEXT, text = "line 41")
            )
        )
        val next = assertIs<Load.Ready<List<RunStreamEvent>>>(now.state.value.log?.second).value
        assertEquals(listOf("line 12", "line 41"), listOf(next.first().text, next.last().text))

        now.toggleLog(item)
        assertNull(now.state.value.log)
    }

    @Test
    fun inputComesFromTheAssembledRunOrTheRunRecord() = runTest {
        routes["GET /pages/pg/runs/1"] = RUN_JSON to HttpStatusCode.OK
        val (client, mock) = core()
        val now = NowViewModel(client.api(::RunsApi), client.api(::RunnersApi), backgroundScope)
        val input = RunInput(InputParts(1, 2, 3, 4, 5, 6, 7), 28)
        val running = ActiveRun(
            page = "pg",
            n = 3,
            runner = "codex",
            model = "gpt-6-luna",
            startedAt = kotlin.time.TestTimeSource().markNow(),
            last = RunActivity.Started,
            input = input
        )

        now.showInput(
            NowItem("p", "pg", "t", 3, null, null, RunGlyph.RUNNING, null, false, running)
        )
        assertEquals(RunKey("pg", 3) to Load.Ready(input), now.state.value.input)
        assertTrue(mock.requests.isEmpty())

        now.showInput(NowItem("p", "pg", "t", 1, null, null, RunGlyph.DONE, null, false))
        runCurrent()
        val recorded = assertIs<Load.Ready<RunInput?>>(now.state.value.input?.second).value
        assertEquals(29230, recorded?.totalEst)
    }

    @Test
    fun declaringAPortSendsTheNameAndReloads() = runTest {
        routes["GET /projects/p/ports"] = PORTS_JSON to HttpStatusCode.OK
        routes["POST /projects/p/ports/8080/declare"] = TARGET_JSON to HttpStatusCode.Created
        val (client, mock) = core()
        val ports = PortsViewModel(client.api(::RunsApi), backgroundScope)

        ports.open("p")
        runCurrent()
        ports.toggleDeclare(8080)
        ports.declare(8080)
        assertTrue(mock.requests.none { it.first.startsWith("POST") })

        ports.setName(8080, " 미리보기 ")
        ports.declare(8080)
        runCurrent()
        val post = mock.requests.single { it.first.startsWith("POST") }
        assertEquals("""{"name":"미리보기"}""", post.second)
        assertTrue(ports.state.value.names.isEmpty())
        assertEquals(2, mock.requests.count { it.first == "GET /projects/p/ports" })
    }

    private companion object {
        const val TREE_JSON = """{"root":"/root","lens":"all","entries":[
            {"path":".madang","type":"dir"},{"path":"a.md","type":"file"}],
            "runs":[],"truncated":false}"""
        const val NO_REPO_JSON = """{"error":"no_repo","message":"not a git repository"}"""
        const val STATUS_NO_REPO = """{"repository":false,"folder":"/root","files":[]}"""
        const val STATUS_REPO =
            """{"repository":true,"folder":"/root","branch":"main","files":[{"path":"a.txt","code":"??"}]}"""
        const val WORKTREES_JSON = """[{"path":"/root","head":"","main":true,"branch":"main"},
            {"path":"/root.wt/pg","head":"","main":false,"page":"pg"}]"""
        const val RUN_JSON = """{"n":1,"usage":{"input":1,"cached":0,"output":1},
            "changed_files":[],"unknown_files":[],"verify":{},
            "input":{"parts":{"system_est":24600,"profile":110,"brief":1840,"ledger":1320,
            "contract":420,"target":900,"request":40},"total_est":29230}}"""
        const val PORTS_JSON = """[{"port":8080,"host":"127.0.0.1","pid":1}]"""
        const val TARGET_JSON =
            """{"name":"미리보기","command":"x","cwd":".","running":false,"ports":[]}"""
    }
}
