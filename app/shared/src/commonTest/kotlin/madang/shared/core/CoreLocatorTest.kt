package madang.shared.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.test.runTest
import madang.api.model.Health

class CoreLocatorTest {

    private val health = Health(Health.Status.OK, "0.1.0")

    /** 응답하는 주소만 health를 돌려주는 탐침. 확인한 주소를 기록한다. */
    private class FakeProbe(var alive: Set<String>, private val health: Health) : HealthProbe {
        val checked = mutableListOf<String>()

        override suspend fun check(baseUrl: String): Health {
            checked += baseUrl
            if (baseUrl in alive) return health
            error("connection refused: $baseUrl")
        }
    }

    private class FakeProcess(var exit: String? = null) : CoreProcess {
        var stopped = false

        override fun exitDetail(): String? = exit

        override fun stop() {
            stopped = true
        }
    }

    @Test
    fun configuredAddressWinsWhenAlive() = runTest {
        val probe = FakeProbe(setOf("http://10.0.0.2:7470"), health)
        val locator = CoreLocator({ 7481 }, probe, launcher = null)

        val result = locator.locate("http://10.0.0.2:7470/")

        assertEquals(LocateResult.Found("http://10.0.0.2:7470", health, false), result)
        assertEquals(listOf("http://10.0.0.2:7470"), probe.checked)
    }

    @Test
    fun portFileIsTriedBeforeDefault() = runTest {
        val probe = FakeProbe(setOf("http://127.0.0.1:7481"), health)
        val locator = CoreLocator({ 7481 }, probe, launcher = null)

        val result = locator.locate(configuredUrl = null)

        assertIs<LocateResult.Found>(result)
        assertEquals("http://127.0.0.1:7481", result.baseUrl)
        assertEquals(listOf("http://127.0.0.1:7481"), probe.checked)
    }

    @Test
    fun fallsBackToDefaultAddressWithoutPortFile() = runTest {
        val probe = FakeProbe(setOf(CoreClient.DEFAULT_BASE_URL), health)
        val locator = CoreLocator({ null }, probe, launcher = null)

        val result = locator.locate(configuredUrl = " ")

        assertIs<LocateResult.Found>(result)
        assertEquals(CoreClient.DEFAULT_BASE_URL, result.baseUrl)
    }

    @Test
    fun failsWithoutLauncherWhenNothingAnswers() = runTest {
        val probe = FakeProbe(emptySet(), health)
        val locator = CoreLocator({ 7481 }, probe, launcher = null)

        val result = locator.locate("http://10.0.0.2:7470")

        assertIs<LocateResult.Failed>(result)
        assertEquals(FailureReason.NOT_RUNNING, result.reason)
        assertEquals(
            listOf("http://10.0.0.2:7470", "http://127.0.0.1:7481", CoreClient.DEFAULT_BASE_URL),
            result.tried
        )
    }

    @Test
    fun launchesCoreAndWaitsForPortFile() = runTest {
        var port: Int? = null
        val probe = FakeProbe(emptySet(), health)
        val steps = mutableListOf<LocateStep>()
        val locator = CoreLocator(
            portFile = { port },
            probe = probe,
            launcher = {
                port = 7490
                probe.alive = setOf("http://127.0.0.1:7490")
                FakeProcess()
            }
        )

        val result = locator.locate(configuredUrl = null, onStep = steps::add)

        assertEquals(LocateResult.Found("http://127.0.0.1:7490", health, true), result)
        assertEquals(
            listOf(
                LocateStep.Probing(CoreClient.DEFAULT_BASE_URL),
                LocateStep.Launching,
                LocateStep.WaitingForStart
            ),
            steps
        )
    }

    @Test
    fun reportsLaunchFailure() = runTest {
        val locator = CoreLocator(
            portFile = { null },
            probe = FakeProbe(emptySet(), health),
            launcher = { throw IllegalStateException("uv: not found") }
        )

        val result = locator.locate(configuredUrl = null)

        assertEquals(
            LocateResult.Failed(
                FailureReason.LAUNCH_FAILED,
                listOf(CoreClient.DEFAULT_BASE_URL),
                "uv: not found"
            ),
            result
        )
    }

    @Test
    fun reportsEarlyExit() = runTest {
        val locator = CoreLocator(
            portFile = { null },
            probe = FakeProbe(emptySet(), health),
            launcher = { FakeProcess(exit = "exit 2: unknown command 'serve'") }
        )

        val result = locator.locate(configuredUrl = null)

        assertIs<LocateResult.Failed>(result)
        assertEquals(FailureReason.EXITED, result.reason)
        assertEquals("exit 2: unknown command 'serve'", result.detail)
    }

    @Test
    fun stopsProcessThatNeverAnswers() = runTest {
        val process = FakeProcess()
        val locator = CoreLocator(
            portFile = { null },
            probe = FakeProbe(emptySet(), health),
            launcher = { process },
            startTimeout = 5.seconds
        )

        val result = locator.locate(configuredUrl = null)

        assertIs<LocateResult.Failed>(result)
        assertEquals(FailureReason.START_TIMEOUT, result.reason)
        assertTrue(process.stopped)
    }
}
