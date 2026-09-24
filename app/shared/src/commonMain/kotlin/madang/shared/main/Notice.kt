package madang.shared.main

import madang.api.model.AskCreatedEvent
import madang.api.model.FlowWaitingEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunResultStatus

/**
 * 시스템 알림 하나. 문구는 화면이 만든다. 알림을 누르면 [project]의 [page]를 연다.
 *
 * @property title 페이지 제목.
 * @property decision 같은 질문이 `ask.created`와 `flow.waiting`으로 두 번 오면 한 번만 알리려는 결정 id.
 */
sealed interface Notice {
    val project: String
    val page: String
    val title: String
    val decision: String? get() = null

    data class Finished(
        override val project: String,
        override val page: String,
        override val title: String,
        val status: RunResultStatus?
    ) : Notice

    data class Failed(
        override val project: String,
        override val page: String,
        override val title: String,
        val error: String
    ) : Notice

    data class Asked(
        override val project: String,
        override val page: String,
        override val title: String,
        val prompt: String,
        override val decision: String?
    ) : Notice
}

/** 알릴 이벤트면 알림으로 바꾼다: run 완료·실패, 묻는 블록, 사람 결정. 아니면 null. */
fun noticeOf(payload: Any, titleOf: (String) -> String): Notice? = when (payload) {
    is RunFinishedEvent -> Notice.Finished(
        payload.project,
        payload.page,
        titleOf(payload.page),
        payload.data.resultStatus
    )

    is RunFailedEvent ->
        Notice.Failed(payload.project, payload.page, titleOf(payload.page), payload.data.error)

    is AskCreatedEvent ->
        Notice.Asked(
            payload.project,
            payload.page,
            titleOf(payload.page),
            payload.data.prompt,
            payload.data.decision
        )

    is FlowWaitingEvent -> payload.data.decision?.let {
        Notice.Asked(
            payload.project,
            payload.page,
            titleOf(payload.page),
            it.question.prompt,
            it.id
        )
    }

    else -> null
}
