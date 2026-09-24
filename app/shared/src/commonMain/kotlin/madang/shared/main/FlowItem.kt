package madang.shared.main

import madang.api.model.BlockHeader
import madang.api.model.PageDetail
import madang.api.model.RunRecord

/** 3열 본문의 한 항목. 블록, run 기록, 또는 보내는 중인 메시지. */
sealed interface FlowItem {
    val key: String

    data class Block(val header: BlockHeader) : FlowItem {
        override val key: String get() = header.id
    }

    data class Run(val record: RunRecord) : FlowItem {
        override val key: String get() = "run-${record.n}"
    }

    /** 보냈지만 core 페이지에 아직 없는 사용자 메시지. */
    data class Pending(val message: PendingMessage) : FlowItem {
        override val key: String get() = message.localId
    }
}

/** 블록 흐름. 각 run은 그 run을 일으킨 메시지 바로 뒤에, 짝이 없으면 끝에 둔다. */
fun pageFlow(page: PageDetail): List<FlowItem> {
    val blockIds = page.blocks.mapTo(mutableSetOf()) { it.id }
    val runsAfter = page.runs.filter { it.trigger?.message in blockIds }
        .groupBy { it.trigger?.message }
    val items = mutableListOf<FlowItem>()
    for (block in page.blocks) {
        items += FlowItem.Block(block)
        runsAfter[block.id].orEmpty().forEach { items += FlowItem.Run(it) }
    }
    page.runs.filter { it.trigger?.message !in blockIds }.forEach { items += FlowItem.Run(it) }
    return items
}
