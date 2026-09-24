package madang.shared.main

import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Instant
import madang.api.model.AskCreatedEvent
import madang.api.model.FlowWaitingEvent
import madang.api.model.PageCard
import madang.api.model.PageDeletedEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunResultStatus
import madang.api.model.RunStartedEvent

/**
 * 카드·실행 블록·지금 탭이 함께 쓰는 실행 상태 글리프.
 *
 * 실행 중(스피너), 사람 필요(호박색 물음표), 완료(초록 체크), 실패(빨간 점), 유휴(회색 점).
 */
enum class RunGlyph { RUNNING, NEEDS_HUMAN, DONE, FAILED, IDLE }

/**
 * 끝난 run의 결과를 글리프로. runner가 멈췄거나 시간이 넘은 것(`error`·`cancelled`·`blocked`)은
 * 실패, 그 밖에 정상으로 끝난 것은 완료다. 결과가 없으면 유휴.
 */
fun resultGlyph(status: RunResultStatus?): RunGlyph = when (status) {
    null -> RunGlyph.IDLE
    RunResultStatus.ERROR, RunResultStatus.CANCELLED, RunResultStatus.BLOCKED -> RunGlyph.FAILED
    else -> RunGlyph.DONE
}

/**
 * 이벤트로 본 끝난 run 하나.
 *
 * @property finished core가 적은 끝난 시각(ISO 8601).
 */
data class FinishedRun(
    val project: String,
    val page: String,
    val n: Int,
    val runner: String?,
    val model: String?,
    val status: RunResultStatus?,
    val finished: String?
)

/**
 * 페이지별 run 상태 중 진행 중 run([ActiveRun]) 밖의 것.
 *
 * @property finished 앱이 켜진 뒤 끝난 페이지별 마지막 run.
 * @property waiting 사람 결정이나 묻는 블록을 기다리는 페이지.
 * @property unread 열려 있지 않을 때 run이 끝나 아직 열어 보지 않은 페이지.
 */
data class RunWatch(
    val finished: Map<String, FinishedRun> = emptyMap(),
    val waiting: Set<String> = emptySet(),
    val unread: Set<String> = emptySet()
) {
    /**
     * 이벤트를 반영한다. [active]는 이 이벤트를 반영하기 전의 진행 중 run이다(`run.failed`에는
     * runner·모델이 없다). [openPage]에서 끝난 run은 이미 보고 있으므로 읽지 않음이 아니다.
     */
    fun withEvent(payload: Any, active: Map<String, ActiveRun>, openPage: String?): RunWatch =
        when (payload) {
            is RunStartedEvent -> copy(waiting = waiting - payload.page)

            is RunFinishedEvent -> ended(
                FinishedRun(
                    project = payload.project,
                    page = payload.page,
                    n = payload.run,
                    runner = payload.data.runner,
                    model = payload.data.model,
                    status = payload.data.resultStatus,
                    finished = payload.data.finished ?: payload.ts
                ),
                openPage
            )

            is RunFailedEvent -> ended(
                FinishedRun(
                    project = payload.project,
                    page = payload.page,
                    n = payload.run,
                    runner = active[payload.page]?.runner,
                    model = active[payload.page]?.model,
                    status = payload.data.resultStatus,
                    finished = payload.ts
                ),
                openPage
            )

            is FlowWaitingEvent -> copy(waiting = waiting + payload.page)

            is AskCreatedEvent -> copy(waiting = waiting + payload.page)

            is PageDeletedEvent -> forget(payload.data.id)

            else -> this
        }

    /** 페이지를 열었다. 읽지 않음을 지운다. */
    fun read(page: String): RunWatch = copy(unread = unread - page)

    /** 불러온 페이지가 기다리는지로 사람 필요를 맞춘다. */
    fun withWaiting(page: String, isWaiting: Boolean): RunWatch =
        copy(waiting = if (isWaiting) waiting + page else waiting - page)

    private fun ended(run: FinishedRun, openPage: String?) = copy(
        finished = finished + (run.page to run),
        waiting = waiting - run.page,
        unread = if (run.page == openPage) unread else unread + run.page
    )

    private fun forget(page: String) =
        copy(finished = finished - page, waiting = waiting - page, unread = unread - page)
}

/**
 * 페이지의 글리프. 진행 중 run → 사람 필요 → 이벤트로 본 끝난 run → 카드의 마지막 run 순서로
 * 본다. run이 없던 페이지는 유휴.
 */
fun glyphOf(page: String, card: PageCard?, active: Map<String, ActiveRun>, watch: RunWatch) = when {
    page in active -> RunGlyph.RUNNING
    page in watch.waiting -> RunGlyph.NEEDS_HUMAN
    else -> resultGlyph(watch.finished[page]?.status ?: card?.lastRun?.resultStatus)
}

/** 지금 탭이 끝난 run을 보여 주는 기간. */
val RECENT_WINDOW: Duration = 30.minutes

/**
 * 지금 탭의 한 줄: 페이지 하나의 진행 중이거나 최근 run.
 *
 * @property n run 번호. 사람을 기다리지만 run 번호를 모르면 null.
 * @property at 정렬 기준 시각: 진행 중이면 시작, 끝났으면 끝난 시각(카드에서 온 것은 갱신 시각).
 * @property active 진행 중이면 그 run.
 */
data class NowItem(
    val project: String,
    val page: String,
    val title: String,
    val n: Int?,
    val runner: String?,
    val model: String?,
    val glyph: RunGlyph,
    val at: Instant?,
    val unread: Boolean,
    val active: ActiveRun? = null
) {
    /** 사람을 기다리는 줄(물음표)은 한 번 눌러도 그 페이지를 연다. 묻는 블록이 거기 있다. */
    val opensOnClick: Boolean get() = glyph == RunGlyph.NEEDS_HUMAN
}

/**
 * 모든 프로젝트의 진행 중·사람 필요·최근 run. 진행 중이 먼저(최근에 시작한 것부터), 다음 사람
 * 필요, 다음 [now]에서 [RECENT_WINDOW] 안에 끝난 run(최근 것부터)이다.
 *
 * 끝난 run은 앱이 이벤트로 본 것([RunWatch.finished])이 우선이고, 앱이 켜지기 전에 끝난 run은
 * 카드의 마지막 run과 갱신 시각으로 보인다.
 */
fun nowItems(
    cards: List<PageCard>,
    active: Map<String, ActiveRun>,
    watch: RunWatch,
    now: Instant
): List<NowItem> {
    val byId = cards.associateBy { it.id }
    val title = { page: String -> byId[page]?.title ?: page }
    val running = active.values.map { run ->
        NowItem(
            project = run.project.ifEmpty { byId[run.page]?.project.orEmpty() },
            page = run.page,
            title = title(run.page),
            n = run.n,
            runner = run.runner,
            model = run.model,
            glyph = RunGlyph.RUNNING,
            at = instantOrNull(run.started),
            unread = false,
            active = run
        )
    }.sortedByDescending { it.at }
    val waiting = (watch.waiting - active.keys).mapNotNull { page ->
        val card = byId[page] ?: return@mapNotNull null
        val last = watch.finished[page]
        NowItem(
            project = card.project,
            page = page,
            title = card.title,
            n = last?.n ?: card.lastRun?.n,
            runner = last?.runner ?: card.lastRun?.runner,
            model = last?.model ?: card.lastRun?.model,
            glyph = RunGlyph.NEEDS_HUMAN,
            at = instantOrNull(last?.finished ?: card.updated),
            unread = page in watch.unread
        )
    }.sortedByDescending { it.at }
    val shown = active.keys + watch.waiting
    val recent = (finishedFromEvents(watch, byId) + finishedFromCards(cards, watch))
        .filter { it.page !in shown }
        .filter { item -> item.at != null && now - item.at <= RECENT_WINDOW }
        .map { it.copy(unread = it.page in watch.unread) }
        .sortedByDescending { it.at }
    return running + waiting + recent
}

private fun finishedFromEvents(watch: RunWatch, cards: Map<String, PageCard>) =
    watch.finished.values.map { run ->
        NowItem(
            project = run.project,
            page = run.page,
            title = cards[run.page]?.title ?: run.page,
            n = run.n,
            runner = run.runner,
            model = run.model,
            glyph = resultGlyph(run.status),
            at = instantOrNull(run.finished),
            unread = false
        )
    }

private fun finishedFromCards(cards: List<PageCard>, watch: RunWatch) = cards
    .filter { it.id !in watch.finished }
    .mapNotNull { card ->
        val last = card.lastRun ?: return@mapNotNull null
        NowItem(
            project = card.project,
            page = card.id,
            title = card.title,
            n = last.n,
            runner = last.runner,
            model = last.model,
            glyph = resultGlyph(last.resultStatus),
            at = instantOrNull(card.updated),
            unread = false
        )
    }
