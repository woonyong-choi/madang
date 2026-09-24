package madang.shared.main

import kotlin.time.TimeMark
import madang.api.model.RunAssembledEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFallbackEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunInput
import madang.api.model.RunProgressEvent
import madang.api.model.RunStartedEvent
import madang.api.model.RunStreamEvent

/** run의 마지막 이벤트 요약. 문구는 화면이 만든다. */
sealed interface RunActivity {
    data object Started : RunActivity

    data class Assembled(val totalEstimate: Int) : RunActivity

    data class Progress(val event: RunStreamEvent) : RunActivity

    data class Fallback(val from: String, val to: String) : RunActivity
}

/**
 * 진행 중인 run 하나. [startedAt]은 앱이 시작 이벤트를 받은 때다(경과 시간용).
 *
 * @property started core가 적은 시작 시각(ISO 8601).
 * @property input `run.assembled`로 받은 입력 구성. 받기 전에는 null.
 */
data class ActiveRun(
    val page: String,
    val n: Int,
    val runner: String,
    val model: String,
    val startedAt: TimeMark,
    val last: RunActivity,
    val project: String = "",
    val started: String? = null,
    val input: RunInput? = null
)

/**
 * run 이벤트를 페이지별 진행 중 run에 반영한다. run 이벤트가 아니면 그대로 돌려준다.
 *
 * 시작에서 생기고 끝남·실패에서 사라진다. 시작을 못 본 run의 중간 이벤트는 버린다.
 */
fun Map<String, ActiveRun>.withRunEvent(payload: Any, now: () -> TimeMark): Map<String, ActiveRun> =
    when (payload) {
        is RunStartedEvent -> this + (payload.page to startedRun(payload, now()))

        is RunAssembledEvent -> update(payload.page, payload.run) {
            RunActivity.Assembled(payload.data.totalEst)
        }.withInput(payload.page, payload.run, payload.data)

        is RunProgressEvent -> update(payload.page, payload.run) {
            RunActivity.Progress(payload.data)
        }

        is RunFallbackEvent -> update(payload.page, payload.run) {
            RunActivity.Fallback(payload.data.from, payload.data.to)
        }

        is RunFinishedEvent -> finish(payload.page, payload.run)

        is RunFailedEvent -> finish(payload.page, payload.run)

        else -> this
    }

private fun startedRun(event: RunStartedEvent, at: TimeMark) = ActiveRun(
    page = event.page,
    n = event.run,
    runner = event.data.runner,
    model = event.data.model,
    startedAt = at,
    last = RunActivity.Started,
    project = event.project,
    started = event.ts
)

private fun Map<String, ActiveRun>.withInput(page: String, n: Int, input: RunInput) =
    this[page]?.takeIf { it.n == n }?.let { this + (page to it.copy(input = input)) } ?: this

private fun Map<String, ActiveRun>.update(
    page: String,
    n: Int?,
    activity: () -> RunActivity
): Map<String, ActiveRun> {
    val run = this[page]?.takeIf { n == null || it.n == n } ?: return this
    return this + (page to run.copy(last = activity()))
}

private fun Map<String, ActiveRun>.finish(page: String, n: Int): Map<String, ActiveRun> =
    if (this[page]?.n == n) this - page else this
