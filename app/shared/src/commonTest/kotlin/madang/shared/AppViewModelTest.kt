package madang.shared

import io.ktor.http.HttpStatusCode
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertIs
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import madang.shared.core.CoreClient
import madang.shared.core.EventTransport
import madang.shared.onboarding.ToolProbe
import madang.shared.onboarding.ToolStatus
import madang.shared.settings.InMemorySettingsStore

/** 화면 전환은 실제 디스패처에서 돈다. 탐침 제한 시간이 가상 시간으로 당겨지지 않게 한다. */
class AppViewModelTest {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    @AfterTest
    fun tearDown() = scope.cancel()

    private fun appWith(homeJson: String): AppViewModel {
        val mock = MockCore(Dispatchers.Default) { request ->
            when (request.url.encodedPath) {
                "/health" -> json(HEALTH_JSON)
                "/home" -> json(homeJson)
                "/spaces" -> json("[]")
                else -> json("{}", HttpStatusCode.NotFound)
            }
        }
        val deps = AppDependencies(
            settings = InMemorySettingsStore(),
            toolProbe = ToolProbe { ToolStatus(null, null) },
            portFile = { { null } },
            launcher = null,
            connect = { CoreClient(it, mock.engine) },
            eventTransport = {
                EventTransport { onOpen, _ ->
                    onOpen()
                    awaitCancellation()
                }
            }
        )
        return AppViewModel(deps, scope)
    }

    private fun AppViewModel.awaitScreen(): Screen = runBlocking {
        withTimeout(10.seconds) { screen.first { it !is Screen.Start } }
    }

    @Test
    fun missingHomeLeadsToOnboarding() {
        val app = appWith("""{"path":"~/.madang","initialized":false}""")

        app.start()

        assertIs<Screen.Onboarding>(app.awaitScreen())
    }

    @Test
    fun existingHomeLeadsToMainAndSettings() {
        val app = appWith("""{"path":"~/.madang","initialized":true}""")

        app.start()
        assertIs<Screen.Main>(app.awaitScreen())

        app.openSettings()
        assertIs<Screen.Settings>(app.screen.value)
        app.closeSettings()
        assertIs<Screen.Main>(app.screen.value)
    }
}
