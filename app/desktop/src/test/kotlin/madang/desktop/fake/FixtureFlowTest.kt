package madang.desktop.fake

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.mapNotNull
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import madang.api.client.DecisionsApi
import madang.api.client.MemoryApi
import madang.api.client.MessagesApi
import madang.api.client.PagesApi
import madang.api.client.RunsApi
import madang.api.client.TrashApi
import madang.api.model.DecisionAnswer
import madang.api.model.MemoryContent
import madang.api.model.MemoryLayer
import madang.api.model.MessageCreate
import madang.api.model.UnknownFileAction
import madang.shared.core.CoreApiException
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow
import madang.shared.core.decodeEvent
import madang.shared.core.resolveUnknownFile

/**
 * 픽스처 가짜 core가 메시지·결정·묻는 블록·되돌리기·메모리·미등록 파일·최근 삭제를 계약대로 흉내
 * 내는지 본다.
 */
class FixtureFlowTest {

    private val home = File(checkNotNull(javaClass.getResource("/fixture-home")).toURI())
    private val fixture = FixtureHome(home, runStep = 5.milliseconds)
    private val page = "2026-09-24-resume"

    private fun client(): CoreClient {
        val spec = File(checkNotNull(System.getProperty("madang.openapiSpec")))
        return CoreClient(engine = FakeCore(ContractExamples.load(spec), true, fixture).engine)
    }

    /** 다음 [count]개 이벤트의 type. 요청 전에 구독을 시작한다. */
    private fun kotlinx.coroutines.CoroutineScope.nextEventTypes(count: Int) =
        async(start = CoroutineStart.UNDISPATCHED) {
            withTimeout(5.seconds) {
                fixture.events.mapNotNull { decodeEvent(it)?.envelope?.type?.value }
                    .take(count).toList()
            }
        }

    @Test
    fun messagePlaysARunAndLeavesAnUnknownFile() = runBlocking {
        client().use { core ->
            val types = nextEventTypes(8)

            val accepted = core.api(::MessagesApi)
                .sendMessage(page, MessageCreate("design: 경력 요약 한 줄 추가")).bodyOrThrow()

            assertEquals("b10", accepted.message)
            assertEquals(
                listOf(
                    "block.added",
                    "run.started",
                    "run.assembled",
                    "run.progress",
                    "block.added",
                    "block.added",
                    "run.finished",
                    "page.unknown_files"
                ),
                types.await()
            )
            val detail = core.api(::PagesApi).getPage(page).bodyOrThrow()
            val run = detail.runs.last()
            assertEquals(3, run.n)
            assertEquals("claude", run.runner)
            assertEquals("b10", run.trigger?.message)
            assertEquals(listOf("blocks/scratch-3.txt"), detail.unknownFiles.map { it.path })
        }
    }

    @Test
    fun decisionWordWaitsUntilAnswered() = runBlocking {
        client().use { core ->
            val types = nextEventTypes(5)
            core.api(::MessagesApi).sendMessage(page, MessageCreate("결정이 필요한 작업"))
                .bodyOrThrow()
            assertEquals("flow.waiting", types.await().last())
            val waiting = core.api(::PagesApi).getPage(page).bodyOrThrow().waiting
            assertEquals("q3", waiting?.decision?.id)

            val finished = nextEventTypes(3)
            core.api(::DecisionsApi).answerDecision(page, "q3", DecisionAnswer("retry"))
                .bodyOrThrow()

            assertEquals("run.finished", finished.await().last())
            assertNull(core.api(::PagesApi).getPage(page).bodyOrThrow().waiting)
        }
    }

    @Test
    fun finishedRunIsPublishedAndUndoUnpublishesItOnce() = runBlocking {
        client().use { core ->
            val types = nextEventTypes(10)
            core.api(::MessagesApi).sendMessage(page, MessageCreate("정리해줘")).bodyOrThrow()
            assertEquals(listOf("page.updated", "publish.done"), types.await().takeLast(2))

            val runs = core.api(::RunsApi)
            val undone = runs.undoRun(page, 3).bodyOrThrow()

            assertEquals(listOf(1), undone.unpublished)
            val again = assertFailsWith<CoreApiException> { runs.undoRun(page, 3).bodyOrThrow() }
            assertEquals(409, again.status)
        }
    }

    @Test
    fun policyWordLeavesAnAskBlockAndMergeAnswerPublishes() = runBlocking {
        client().use { core ->
            val types = nextEventTypes(12)
            core.api(::MessagesApi).sendMessage(page, MessageCreate("정책에 걸릴 작업")).bodyOrThrow()
            assertEquals(
                listOf("block.added", "flow.waiting", "ask.created"),
                types.await().takeLast(3)
            )
            val decision = core.api(::PagesApi).getPage(page).bodyOrThrow().waiting?.decision
            val ask = checkNotNull(decision?.ask)
            assertEquals(listOf("merge", "retry", "stop"), decision.question.options)

            val decisions = core.api(::DecisionsApi)
            val wrong = assertFailsWith<CoreApiException> {
                decisions.answerAsk(page, ask, DecisionAnswer("maybe")).bodyOrThrow()
            }
            assertEquals(400, wrong.status)
            val resumed = nextEventTypes(3)
            decisions.answerAsk(page, ask, DecisionAnswer("merge")).bodyOrThrow()

            assertEquals(listOf("block.added", "publish.done", "page.updated"), resumed.await())
            assertNull(core.api(::PagesApi).getPage(page).bodyOrThrow().waiting)
        }
    }

    @Test
    fun invalidLedgerIsRejectedWithLines() = runBlocking {
        client().use { core ->
            val api = core.api(::MemoryApi)
            val ledger = api.getMemory(page).bodyOrThrow().ledger
            assertEquals(2000, ledger.tokenLimit)

            val broken = ledger.content.replace("status: review", "status: finished")
            val error = assertFailsWith<CoreApiException> {
                api.saveMemory(page, MemoryLayer.LEDGER, MemoryContent(broken)).bodyOrThrow()
            }
            assertEquals(400, error.status)
            assertEquals(listOf(2), error.issues.map { it.line })

            val fixed = ledger.content.replace("status: review", "status: doing")
            val saved = api.saveMemory(page, MemoryLayer.LEDGER, MemoryContent(fixed)).bodyOrThrow()
            assertEquals(fixed, saved.content)
        }
    }

    @Test
    fun unknownFileIsResolvedByEncodedPath() = runBlocking {
        client().use { core ->
            val types = nextEventTypes(8)
            core.api(::MessagesApi).sendMessage(page, MessageCreate("정리해줘")).bodyOrThrow()
            types.await()

            val remaining = core.resolveUnknownFile(
                page,
                "blocks/scratch-3.txt",
                UnknownFileAction(UnknownFileAction.Action.KEEP)
            )

            assertTrue(remaining.isEmpty())
        }
    }

    @Test
    fun deletedPageCanBeRestored() = runBlocking {
        client().use { core ->
            core.api(::PagesApi).deletePage("2026-09-20-cover-letter").bodyOrThrow()
            val trash = core.api(::TrashApi)
            val entry = trash.listTrash().bodyOrThrow().single()
            assertEquals("2026-09-20-cover-letter", entry.page)
            assertEquals(listOf(".madang/pages/2026-09-20-cover-letter"), entry.paths)

            assertEquals(entry.id, trash.restoreTrash(entry.id).bodyOrThrow().id)

            assertTrue(trash.listTrash().bodyOrThrow().isEmpty())
            assertEquals(
                "2026-09-20-cover-letter",
                core.api(::PagesApi).getPage("2026-09-20-cover-letter").bodyOrThrow().id
            )
        }
    }
}
