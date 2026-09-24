package madang.shared.main

import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.MessageRole
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

/**
 * 접힌 항목의 key.
 *
 * router 메시지와 run은 늘 접히고, user·agent 메시지는 마지막 user 메시지보다 앞이면
 * (지난 대화면) 접힌다. doc·data·view는 접히지 않는다. [expandAll]이면 아무것도 접지 않고,
 * [toggled]에 있는 항목은 규칙과 반대로 둔다.
 */
fun foldedKeys(items: List<FlowItem>, expandAll: Boolean, toggled: Set<String>): Set<String> {
    if (expandAll) return emptySet()
    val lastUser = items.indexOfLast {
        it is FlowItem.Pending ||
            (it is FlowItem.Block && it.header.isMessage(MessageRole.USER))
    }
    return items.withIndex()
        .filter { (index, item) -> foldsByRule(item, index < lastUser) != (item.key in toggled) }
        .mapTo(mutableSetOf()) { it.value.key }
}

/** 접힐 수 있는 항목인가. 접을 수 없는 항목은 클릭으로도 접지 않는다. */
fun isFoldable(item: FlowItem): Boolean = when (item) {
    is FlowItem.Run -> true
    is FlowItem.Block -> item.header.type == BlockType.MESSAGE
    is FlowItem.Pending -> false
}

private fun foldsByRule(item: FlowItem, old: Boolean): Boolean = when (item) {
    is FlowItem.Run -> true

    is FlowItem.Pending -> false

    is FlowItem.Block -> when {
        item.header.type != BlockType.MESSAGE -> false
        item.header.role == MessageRole.ROUTER -> true
        else -> old
    }
}

private fun BlockHeader.isMessage(role: MessageRole) =
    type == BlockType.MESSAGE && this.role == role
