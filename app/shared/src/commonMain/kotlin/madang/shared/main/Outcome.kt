package madang.shared.main

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import madang.api.model.AskCreatedEvent
import madang.api.model.PublishDoneEvent
import madang.api.model.RunRecord

/** 결과 뒤 정책 단계(자동 머지·게시)의 상태. */
enum class SettleState {
    /** run은 끝났고 core 흐름이 아직 진행 중이다(페이지 `busy`). */
    PENDING,

    /** 머지했거나 게시했다. */
    DONE,

    /** 정책이 멈추고 묻는 블록을 남겼다. */
    REFUSED
}

/**
 * core recorder가 run마다 남기는 되돌리기 기록(`runs/<n>.undo.json`)에서 앱이 보는 부분.
 *
 * @property undone 되돌린 시각. 아직이면 null.
 */
@Serializable
data class UndoLog(
    val n: Int,
    val effects: List<UndoEffect> = emptyList(),
    val undone: String? = null
)

/**
 * 부작용 하나.
 *
 * @property kind `file`, `repo`, `commit`, `merge`, `publish` 중 하나.
 * @property commit 커밋·머지 해시.
 * @property publish 게시 번호.
 */
@Serializable
data class UndoEffect(
    val kind: String,
    val commit: String? = null,
    val publish: Int? = null,
    val reverted: String? = null,
    val undone: Boolean = false
)

/** 페이지 기록 폴더 [folder]의 run [n] 되돌리기 기록 경로. */
fun undoLogFile(folder: String, n: Int): String = "$folder/runs/$n.undo.json"

/** 되돌리기 기록 원문을 읽는다. 모양이 다르면 null. */
fun parseUndoLog(text: String): UndoLog? = try {
    UNDO_JSON.decodeFromString(UndoLog.serializer(), text)
} catch (e: SerializationException) {
    null
} catch (e: IllegalArgumentException) {
    null
}

/**
 * 앱이 이 세션에 이벤트로 본 정책 단계.
 *
 * @property asked 정책이 멈추고 묻는 블록을 남긴 run(`ask.created`).
 * @property published run별 게시 번호(`publish.done`).
 * @property undone 이 세션에 되돌린 run.
 */
data class SettleWatch(
    val asked: Set<Int> = emptySet(),
    val published: Map<Int, Int> = emptyMap(),
    val undone: Set<Int> = emptySet()
) {
    /** 열린 페이지의 이벤트 [payload]를 반영한다. core가 알린 사실만 담는다. */
    fun withEvent(payload: Any): SettleWatch = when (payload) {
        is AskCreatedEvent -> payload.run?.let { copy(asked = asked + it) } ?: this

        is PublishDoneEvent -> {
            val run = payload.run
            if (payload.data.undo || run == null) {
                this
            } else {
                copy(published = published + (run to payload.data.n))
            }
        }

        else -> this
    }
}

/**
 * 결과 블록 하나: 끝난 run [n]의 정책 단계와 되돌리기 상태.
 *
 * @property settle 정책 단계 상태. 정책이 할 일이 없었거나 모르면 null.
 * @property merged 머지 커밋 해시.
 * @property published 게시 번호.
 * @property undone 되돌렸다.
 */
data class RunOutcome(
    val n: Int,
    val settle: SettleState?,
    val merged: String? = null,
    val published: Int? = null,
    val undone: Boolean = false
)

/**
 * 끝난 run [run]의 결과. core가 준 사실만 쓴다: 되돌리기 기록의 머지·게시, `ask.created`·기다리는
 * 결정의 묻는 블록 [asked], `publish.done`, 페이지 `busy`. 머지나 게시가 있으면 완료, 묻는 블록이
 * 있으면 거부, [flowBusy]면 대기다.
 */
fun runOutcome(
    run: RunRecord,
    log: UndoLog?,
    asked: Set<Int>,
    watch: SettleWatch,
    flowBusy: Boolean = false
): RunOutcome {
    val n = run.n
    val effects = log?.takeIf { it.n == n }?.effects.orEmpty()
    val merged = effects.lastOrNull { it.kind == MERGE_EFFECT }?.commit
    val published = effects.lastOrNull { it.kind == PUBLISH_EFFECT }?.publish
        ?: watch.published[n]
    val settle = when {
        merged != null || published != null -> SettleState.DONE
        n in asked -> SettleState.REFUSED
        flowBusy -> SettleState.PENDING
        else -> null
    }
    val undone = log?.takeIf { it.n == n }?.undone != null || n in watch.undone
    return RunOutcome(n, settle, merged, published, undone)
}

/** 결과 블록을 보일 run: 마지막으로 끝난 run. 끝난 run이 없으면 null. */
fun lastFinishedRun(runs: List<RunRecord>): RunRecord? =
    runs.lastOrNull { it.finished != null || it.resultStatus != null }

private const val MERGE_EFFECT = "merge"
private const val PUBLISH_EFFECT = "publish"
private val UNDO_JSON = Json { ignoreUnknownKeys = true }
