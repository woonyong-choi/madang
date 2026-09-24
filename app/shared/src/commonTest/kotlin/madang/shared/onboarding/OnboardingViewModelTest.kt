package madang.shared.onboarding

import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import madang.api.model.ConfigDocument
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.json

@OptIn(ExperimentalCoroutinesApi::class)
class OnboardingViewModelTest {

    /** claude를 받은 경로로 확인했다고 남기고 로그인 상태를 돌려준다. */
    private val probedBins = mutableListOf<String>()
    private val loggedIn = ClaudeProbe { bin ->
        probedBins += bin
        ClaudeStatus(installed = true, loggedIn = true, authMethod = "claude.ai")
    }

    /** 로그인 셸 대신 표에서 도구를 찾는다. [executables]에 있는 경로만 실행 파일이다. */
    private class TableLocator(
        val found: Map<String, String>,
        val executables: Set<String> = emptySet()
    ) : ToolLocator {
        override suspend fun locate(tool: String): String? = found[tool]

        override suspend fun isExecutable(path: String): Boolean = path in executables
    }

    private val bothFound = TableLocator(mapOf("claude" to CLAUDE_BIN, "codex" to CODEX_BIN))

    private fun TestScope.viewModel(
        mock: MockCore,
        probe: ClaudeProbe = loggedIn,
        locator: ToolLocator = bothFound,
        onDone: () -> Unit = {}
    ) = OnboardingViewModel(CoreClient(engine = mock.engine), probe, locator, HOME, this, onDone)

    /** 저장된 config.yaml 원문. `PUT /config`가 바꾼다. */
    private var savedConfig = CONFIG

    private fun TestScope.okCore(configStatus: HttpStatusCode = HttpStatusCode.OK) =
        MockCore(this) { request ->
            when (request.url.encodedPath) {
                "/home" -> json("""{"path":"$HOME","initialized":true}""")

                "/projects" -> json(
                    """{"id":"madang","title":"madang","path":"/work/madang"}""",
                    HttpStatusCode.Created
                )

                "/config" -> {
                    if (request.method == HttpMethod.Put && configStatus == HttpStatusCode.OK) {
                        savedConfig = CoreClient.CoreJson.decodeFromString<ConfigDocument>(
                            (request.body as TextContent).text
                        ).text
                    }
                    if (configStatus == HttpStatusCode.OK) {
                        json(CoreClient.CoreJson.encodeToString(ConfigDocument(savedConfig)))
                    } else {
                        json(
                            """{"error":"invalid","message":"bad config","issues":[]}""",
                            configStatus
                        )
                    }
                }

                else -> json("{}", HttpStatusCode.NotFound)
            }
        }

    private suspend fun TestScope.reachTools(vm: OnboardingViewModel) {
        vm.start()
        advanceUntilIdle()
        vm.setProjectPath("/work/madang")
        vm.registerProject()
        advanceUntilIdle()
    }

    @Test
    fun initializesHomeRegistersProjectThenChecksClaude() = runTest {
        val mock = okCore()
        var done = false
        val vm = viewModel(mock) { done = true }

        vm.start()
        advanceUntilIdle()
        assertEquals(OnboardingStep.PROJECT, vm.state.value.step)
        assertEquals("POST /home" to """{"path":"$HOME"}""", mock.requests.single())

        vm.setProjectPath("/work/madang")
        vm.registerProject()
        advanceUntilIdle()
        val tools = vm.state.value
        assertEquals(OnboardingStep.TOOLS, tools.step)
        assertEquals("POST /projects" to """{"path":"/work/madang"}""", mock.requests[1])
        assertEquals(ClaudeStatus(true, true, "claude.ai"), tools.claude)

        vm.finish()
        assertTrue(done)
        assertTrue(vm.state.value.done)
    }

    @Test
    fun blankFolderCannotBeRegistered() = runTest {
        val mock = okCore()
        val vm = viewModel(mock)
        vm.start()
        advanceUntilIdle()

        vm.setProjectPath("  ")
        vm.registerProject()
        advanceUntilIdle()

        assertFalse(vm.state.value.canRegisterProject)
        assertEquals(OnboardingStep.PROJECT, vm.state.value.step)
        assertEquals(1, mock.requests.size)
    }

    @Test
    fun homeFailureCanBeRetried() = runTest {
        var fail = true
        val mock = MockCore(this) {
            if (fail) {
                json("""{"error":"conflict","message":"old layout"}""", HttpStatusCode.Conflict)
            } else {
                json("""{"path":"$HOME","initialized":true}""")
            }
        }
        val vm = viewModel(mock)

        vm.start()
        advanceUntilIdle()
        assertEquals(OnboardingStep.HOME, vm.state.value.step)
        assertEquals("conflict: old layout", vm.state.value.error)
        assertFalse(vm.state.value.submitting)

        fail = false
        vm.start()
        advanceUntilIdle()
        assertEquals(OnboardingStep.PROJECT, vm.state.value.step)
        assertNull(vm.state.value.error)
    }

    @Test
    fun rejectedFolderStaysOnProjectStep() = runTest {
        val mock = MockCore(this) { request ->
            when (request.url.encodedPath) {
                "/home" -> json("""{"path":"$HOME","initialized":true}""")

                else -> json(
                    """{"error":"not_found","message":"folder not found"}""",
                    HttpStatusCode.NotFound
                )
            }
        }
        val vm = viewModel(mock)
        vm.start()
        advanceUntilIdle()

        vm.setProjectPath("/nowhere")
        vm.registerProject()
        advanceUntilIdle()

        assertEquals(OnboardingStep.PROJECT, vm.state.value.step)
        assertEquals("not_found: folder not found", vm.state.value.error)
    }

    @Test
    fun foundToolsAreSavedAsRunnerBinsAndClaudeIsCheckedWithThatPath() = runTest {
        val mock = okCore()
        val vm = viewModel(mock)

        reachTools(vm)

        val state = vm.state.value
        assertEquals(ToolState(path = CLAUDE_BIN), state.tool("claude"))
        assertEquals(ToolState(path = CODEX_BIN), state.tool("codex"))
        assertEquals(
            listOf("GET /config", "PUT /config"),
            mock.requests.map { it.first }.filter { it.endsWith("/config") }
        )
        assertEquals(
            CONFIG.replace("bin: claude", "bin: \"$CLAUDE_BIN\"")
                .replace("bin: codex", "bin: \"$CODEX_BIN\""),
            savedConfig
        )
        assertEquals(listOf(CLAUDE_BIN), probedBins)
        assertNull(state.error)
    }

    @Test
    fun missingToolIsNotSavedAndClaudeIsNotInstalled() = runTest {
        val mock = okCore()
        val vm = viewModel(mock, locator = TableLocator(emptyMap()))

        reachTools(vm)

        val state = vm.state.value
        assertTrue(state.tool("claude").missing)
        assertTrue(state.tool("codex").missing)
        assertEquals(ClaudeStatus(installed = false, loggedIn = false), state.claude)
        assertTrue(mock.requests.none { it.first.endsWith("/config") })
        assertTrue(probedBins.isEmpty())
        assertEquals(CONFIG, savedConfig)
    }

    @Test
    fun chosenPathIsCheckedSavedAndProbed() = runTest {
        val chosen = "/Users/me/.local/bin/claude"
        val vm = viewModel(
            okCore(),
            locator = TableLocator(mapOf("codex" to CODEX_BIN), executables = setOf(chosen))
        )
        reachTools(vm)
        assertTrue(vm.state.value.tool("claude").missing)

        vm.setToolInput("claude", "/Users/me/notes.txt")
        vm.useToolInput("claude")
        advanceUntilIdle()
        assertTrue(vm.state.value.tool("claude").rejected)
        assertTrue(vm.state.value.tool("claude").missing)

        vm.setToolInput("claude", " $chosen ")
        vm.useToolInput("claude")
        advanceUntilIdle()

        val claude = vm.state.value.tool("claude")
        assertEquals(chosen, claude.path)
        assertFalse(claude.rejected)
        assertTrue(savedConfig.contains("bin: \"$chosen\""))
        assertTrue(savedConfig.contains("bin: \"$CODEX_BIN\""))
        assertEquals(listOf(chosen), probedBins)
        assertEquals(ClaudeStatus(true, true, "claude.ai"), vm.state.value.claude)
    }

    @Test
    fun rejectedConfigIsReportedButClaudeIsStillChecked() = runTest {
        val vm = viewModel(okCore(HttpStatusCode.BadRequest))

        reachTools(vm)

        assertEquals("invalid: bad config", vm.state.value.error)
        assertEquals(listOf(CLAUDE_BIN), probedBins)
    }

    @Test
    fun recheckLooksUpToolsAgain() = runTest {
        val found = mutableMapOf<String, String>()
        val locator = object : ToolLocator {
            override suspend fun locate(tool: String): String? = found[tool]

            override suspend fun isExecutable(path: String): Boolean = false
        }
        val vm = viewModel(okCore(), locator = locator)
        reachTools(vm)
        assertEquals(ClaudeStatus(installed = false, loggedIn = false), vm.state.value.claude)

        found["claude"] = CLAUDE_BIN
        vm.checkTools()
        advanceUntilIdle()

        assertEquals(CLAUDE_BIN, vm.state.value.tool("claude").path)
        assertEquals(ClaudeStatus(true, true, "claude.ai"), vm.state.value.claude)
        assertTrue(savedConfig.contains("bin: \"$CLAUDE_BIN\""))
    }

    private companion object {
        const val HOME = "/home/me/.madang"
        const val CLAUDE_BIN = "/home/me/.local/bin/claude"
        const val CODEX_BIN = "/opt/homebrew/bin/codex"
        val CONFIG = """
            # 도구 경로
            runners:
              claude:
                bin: claude
              codex:
                bin: codex
        """.trimIndent() + "\n"
    }
}
