package madang.shared.onboarding

import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.json

class OnboardingViewModelTest {

    private val loggedIn = ClaudeProbe {
        ClaudeStatus(installed = true, loggedIn = true, authMethod = "claude.ai")
    }

    private fun TestScope.viewModel(
        mock: MockCore,
        probe: ClaudeProbe = loggedIn,
        onDone: () -> Unit = {}
    ) = OnboardingViewModel(CoreClient(engine = mock.engine), probe, HOME, this, onDone)

    private fun TestScope.okCore() = MockCore(this) { request ->
        when (request.url.encodedPath) {
            "/home" -> json("""{"path":"$HOME","initialized":true}""")

            "/projects" -> json(
                """{"id":"madang","title":"madang","path":"/work/madang"}""",
                HttpStatusCode.Created
            )

            else -> json("{}", HttpStatusCode.NotFound)
        }
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
        val claude = vm.state.value
        assertEquals(OnboardingStep.CLAUDE, claude.step)
        assertEquals("POST /projects" to """{"path":"/work/madang"}""", mock.requests.last())
        assertEquals(ClaudeStatus(true, true, "claude.ai"), claude.claude)

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
    fun missingClaudeIsReportedAndCanBeRechecked() = runTest {
        var installed = false
        val probe = ClaudeProbe { ClaudeStatus(installed = installed, loggedIn = false) }
        val vm = viewModel(okCore(), probe)
        vm.start()
        advanceUntilIdle()
        vm.setProjectPath("/work/madang")
        vm.registerProject()
        advanceUntilIdle()
        assertEquals(ClaudeStatus(installed = false, loggedIn = false), vm.state.value.claude)

        installed = true
        vm.checkClaude()
        advanceUntilIdle()
        assertEquals(ClaudeStatus(installed = true, loggedIn = false), vm.state.value.claude)
    }

    private companion object {
        const val HOME = "/home/me/.madang"
    }
}
