package madang.desktop.fake

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import madang.api.client.BlocksApi
import madang.api.client.PagesApi
import madang.api.client.SpacesApi
import madang.api.model.PageUpdate
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow
import madang.shared.core.decodeEvent

class FixtureHomeTest {

    private val home = File(checkNotNull(javaClass.getResource("/fixture-home")).toURI())

    private fun client(fixture: FixtureHome): CoreClient {
        val spec = File(checkNotNull(System.getProperty("madang.openapiSpec")))
        return CoreClient(engine = FakeCore(ContractExamples.load(spec), true, fixture).engine)
    }

    @Test
    fun servesSpacesWithCountsAndPinnedCardsFirst() = runBlocking {
        client(FixtureHome(home)).use { core ->
            val spaces = core.api(::SpacesApi).listSpaces().bodyOrThrow()
            val jobs = spaces.first { it.slug == "jobs" }
            assertEquals(2, jobs.pages)

            val cards = core.api(::PagesApi).listPages("jobs").bodyOrThrow()
            assertEquals(listOf("2026-09-24-resume", "2026-09-23-posting"), cards.map { it.id })
            val resume = cards.first()
            assertEquals(
                mapOf("message" to 6, "view" to 1, "data" to 2, "run" to 2),
                resume.blockCounts
            )
            assertEquals("codex", resume.lastRun?.runner)
            assertEquals("b04", resume.firstView)
            assertTrue(resume.preview!!.startsWith("work 순서를"))
        }
    }

    @Test
    fun servesBlockFilesAndEveryInitialEventDecodes() = runBlocking {
        val fixture = FixtureHome(home)
        client(fixture).use { core ->
            val doc = core.api(::BlocksApi).getBlock("2026-09-24-session-bug", "b04").bodyOrThrow()
            assertTrue(doc.content.contains("```mermaid"))
        }
        assertTrue(fixture.initialEvents.isNotEmpty())
        assertTrue(fixture.initialEvents.all { decodeEvent(it) != null })
    }

    @Test
    fun pageUpdateChangesCardAndEmitsEvent() = runBlocking {
        val fixture = FixtureHome(home)
        client(fixture).use { core ->
            val pages = core.api(::PagesApi)
            val next = async { fixture.events.first() }
            yield()

            val card = pages.updatePage("2026-09-10-gc", PageUpdate(pinned = true, space = "root"))
                .bodyOrThrow()

            assertEquals("root", card.space)
            assertTrue(card.pinned)
            val event = decodeEvent(next.await())
            assertEquals("page.updated", event?.envelope?.type?.value)
            val pinned = pages.listPages("root").bodyOrThrow().filter { it.pinned }
            assertEquals(listOf("2026-09-10-gc"), pinned.map { it.id })
        }
    }
}
