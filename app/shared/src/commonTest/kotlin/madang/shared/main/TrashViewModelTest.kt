package madang.shared.main

import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import madang.api.client.TrashApi
import madang.shared.MockCore
import madang.shared.core.CoreClient
import madang.shared.json

@OptIn(ExperimentalCoroutinesApi::class)
class TrashViewModelTest {

    private val entry = """{"commit":"9f8e7d6","deleted":"2026-09-23T18:02:11+09:00",
        "space":"jobs","page":"2026-09-20-cover-letter","block":null,
        "paths":["spaces/jobs/pages/2026-09-20-cover-letter"],
        "message":"[2026-09-20-cover-letter] delete page"}"""

    @Test
    fun restoreReloadsTheListAndNotifies() = runTest {
        var trash = "[$entry]"
        var restored = 0
        val mock = MockCore(this) { request ->
            when (request.url.encodedPath) {
                "/trash" -> json(trash)

                "/trash/9f8e7d6/restore" -> {
                    trash = "[]"
                    json("""{"commit":"0a1b2c3","paths":["spaces/jobs/pages/x"]}""")
                }

                else -> json("""{"error":"not_found","message":"x"}""", HttpStatusCode.NotFound)
            }
        }
        val api = CoreClient("http://core", mock.engine).api(::TrashApi)
        val viewModel = TrashViewModel(api, backgroundScope) { restored++ }

        viewModel.load()
        runCurrent()
        assertEquals(listOf("9f8e7d6"), viewModel.state.value.entries?.map { it.commit })

        viewModel.restore("9f8e7d6")
        assertEquals("9f8e7d6", viewModel.state.value.restoring)
        runCurrent()

        assertTrue("POST /trash/9f8e7d6/restore" to null in mock.requests)
        assertEquals(emptyList(), viewModel.state.value.entries)
        assertNull(viewModel.state.value.restoring)
        assertEquals(1, restored)
    }

    @Test
    fun failedRestoreShowsTheCause() = runTest {
        val mock = MockCore(this) { request ->
            when (request.url.encodedPath) {
                "/trash" -> json("[$entry]")

                else -> json(
                    """{"error":"conflict","message":"path exists"}""",
                    HttpStatusCode.Conflict
                )
            }
        }
        val api = CoreClient("http://core", mock.engine).api(::TrashApi)
        val viewModel = TrashViewModel(api, backgroundScope) {}
        viewModel.load()
        runCurrent()

        viewModel.restore("9f8e7d6")
        runCurrent()

        assertEquals("conflict: path exists", viewModel.state.value.error)
        assertNull(viewModel.state.value.restoring)
    }
}
