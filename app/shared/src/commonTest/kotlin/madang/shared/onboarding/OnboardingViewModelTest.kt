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
import madang.shared.RUNNERS_JSON
import madang.shared.core.CoreClient
import madang.shared.json
import madang.shared.settings.InMemorySettingsStore

class OnboardingViewModelTest {

    private val installed =
        ToolProbe { ToolStatus(path = "/usr/local/bin/$it", version = "$it 1.0") }

    private fun TestScope.viewModel(
        mock: MockCore,
        store: InMemorySettingsStore = InMemorySettingsStore(),
        onDone: () -> Unit = {}
    ) = OnboardingViewModel(CoreClient(engine = mock.engine), installed, store, this, onDone)

    private fun TestScope.okCore() = MockCore(this) { request ->
        when (request.url.encodedPath) {
            "/runners" -> json(RUNNERS_JSON)
            "/home" -> json("""{"path":"~/work/madang","initialized":true}""")
            else -> json("{}", HttpStatusCode.NotFound)
        }
    }

    @Test
    fun walksThroughStepsAndInitializesHome() = runTest {
        val mock = okCore()
        val store = InMemorySettingsStore()
        var done = false
        val vm = viewModel(mock, store) { done = true }

        vm.setHomePath("~/work/madang")
        vm.next()
        assertEquals(OnboardingStep.REMOTE, vm.state.value.step)

        vm.setRemote("git@github.com:me/madang-home.git")
        vm.next()
        advanceUntilIdle()
        val tools = vm.state.value
        assertEquals(OnboardingStep.TOOLS, tools.step)
        assertTrue(tools.tools.all { it.status?.installed == true })
        assertEquals(listOf("claude", "codex"), tools.runners.map { it.name })

        vm.next()
        assertEquals(OnboardingStep.PERMISSIONS, vm.state.value.step)
        vm.later()
        advanceUntilIdle()

        assertTrue(done)
        assertTrue(vm.state.value.done)
        assertEquals(
            "POST /home" to
                """{"path":"~/work/madang","remote":"git@github.com:me/madang-home.git"}""",
            mock.requests.last()
        )
        assertEquals("~/work/madang", store.load().homePath)
    }

    @Test
    fun defaultHomeIsNotStoredAndRemoteIsOptional() = runTest {
        val mock = okCore()
        val store = InMemorySettingsStore()
        val vm = viewModel(mock, store)

        repeat(3) { vm.next() }
        vm.later()
        advanceUntilIdle()

        assertEquals("POST /home" to """{"path":"~/.madang"}""", mock.requests.last())
        assertNull(store.load().homePath)
    }

    @Test
    fun blankHomeBlocksNext() = runTest {
        val vm = viewModel(okCore())
        vm.setHomePath("  ")

        vm.next()

        assertFalse(vm.state.value.canGoNext)
        assertEquals(OnboardingStep.HOME, vm.state.value.step)
    }

    @Test
    fun invalidRemoteStaysOnStep() = runTest {
        val vm = viewModel(okCore())
        vm.next()

        vm.setRemote("not a url")
        vm.next()

        assertEquals(OnboardingStep.REMOTE, vm.state.value.step)
        assertTrue(vm.state.value.remoteInvalid)
        vm.setRemote("https://example.com/me/home.git")
        assertFalse(vm.state.value.remoteInvalid)
    }

    @Test
    fun backReturnsToPreviousStep() = runTest {
        val vm = viewModel(okCore())
        vm.back()
        assertEquals(OnboardingStep.HOME, vm.state.value.step)

        vm.next()
        vm.back()
        assertEquals(OnboardingStep.HOME, vm.state.value.step)
    }

    @Test
    fun initFailureKeepsUserOnLastStep() = runTest {
        val mock = MockCore(this) { request ->
            when (request.url.encodedPath) {
                "/runners" -> json(RUNNERS_JSON)

                else -> json(
                    """{"error":"conflict","message":"home exists"}""",
                    HttpStatusCode.Conflict
                )
            }
        }
        var done = false
        val vm = viewModel(mock) { done = true }
        repeat(3) { vm.next() }
        advanceUntilIdle()

        vm.later()
        advanceUntilIdle()

        val state = vm.state.value
        assertEquals(OnboardingStep.PERMISSIONS, state.step)
        assertEquals("conflict: home exists", state.error)
        assertFalse(state.submitting)
        assertFalse(done)
    }

    @Test
    fun missingToolIsReported() = runTest {
        val probe = ToolProbe {
            if (it == "codex") ToolStatus(null, null) else ToolStatus("/bin/claude", "2.1")
        }
        val vm = OnboardingViewModel(
            CoreClient(engine = okCore().engine),
            probe,
            InMemorySettingsStore(),
            this
        ) {}
        repeat(2) { vm.next() }
        advanceUntilIdle()

        val byName = vm.state.value.tools.associate { it.name to it.status?.installed }
        assertEquals(mapOf("claude" to true, "codex" to false), byName)
    }

    @Test
    fun remoteAddressShapes() {
        assertTrue(isRemoteAddress("git@github.com:me/home.git"))
        assertTrue(isRemoteAddress("ssh://git@host/home.git"))
        assertTrue(isRemoteAddress("https://github.com/me/home.git"))
        assertFalse(isRemoteAddress("github.com/me/home"))
        assertFalse(isRemoteAddress("git@github.com"))
    }
}
