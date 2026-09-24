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

    private val entryId = "20260923T180211045122-page"

    private val entry = """{"id":"$entryId","deleted":"2026-09-23T18:02:11+09:00",
        "project":"jobs","page":"2026-09-20-cover-letter","block":null,
        "paths":[".madang/pages/2026-09-20-cover-letter"]}"""

    @Test
    fun restoreReloadsTheListAndNotifies() = runTest {
        var trash = "[$entry]"
        var restored = 0
        val mock = MockCore(this) { request ->
            when (request.url.encodedPath) {
                "/trash" -> json(trash)

                "/trash/$entryId/restore" -> {
                    trash = "[]"
                    json("""{"id":"$entryId","paths":[".madang/pages/2026-09-20-cover-letter"]}""")
                }

                else -> json("""{"error":"not_found","message":"x"}""", HttpStatusCode.NotFound)
            }
        }
        val api = CoreClient("http://core", mock.engine).api(::TrashApi)
        val viewModel = TrashViewModel(api, backgroundScope) { restored++ }

        viewModel.load()
        runCurrent()
        assertEquals(listOf(entryId), viewModel.state.value.entries?.map { it.id })

        viewModel.restore(entryId)
        assertEquals(entryId, viewModel.state.value.restoring)
        runCurrent()

        assertTrue("POST /trash/$entryId/restore" to null in mock.requests)
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

        viewModel.restore(entryId)
        runCurrent()

        assertEquals("conflict: path exists", viewModel.state.value.error)
        assertNull(viewModel.state.value.restoring)
    }
}
