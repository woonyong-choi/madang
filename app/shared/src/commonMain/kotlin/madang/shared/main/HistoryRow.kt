package madang.shared.main

import madang.api.model.MessageRole
import madang.api.model.PageDetail
import madang.api.model.RunRecord

/**
 * 기록 탭의 한 줄: 페이지의 run 하나.
 *
 * @property reason 그 run을 고른 router 메시지(`kind=… → runner/model`). 없으면 null.
 */
data class HistoryRow(val run: RunRecord, val reason: String?) {
    val n: Int get() = run.n
    val glyph: RunGlyph get() = resultGlyph(run.resultStatus)
}

/** 열린 페이지의 run, 최근 것부터. 이유는 같은 run 번호의 router 메시지다. */
fun historyRows(page: PageDetail): List<HistoryRow> {
    val reasons = page.blocks
        .filter { it.role == MessageRole.ROUTER && it.run != null }
        .associate { checkNotNull(it.run) to it.text }
    return page.runs.sortedByDescending { it.n }.map { HistoryRow(it, reasons[it.n]) }
}
