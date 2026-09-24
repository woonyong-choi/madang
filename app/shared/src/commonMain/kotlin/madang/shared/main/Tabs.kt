package madang.shared.main

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageDetail

/** 가운데 열에서 페이지 탭 옆에 여는 탭. 탭은 화면 배치일 뿐이고 닫아도 블록은 남는다. */
@Serializable
sealed interface BlockTab {
    /** doc·data 블록. */
    @Serializable
    @SerialName("block")
    data class Block(val id: String) : BlockTab

    /** run 기록. */
    @Serializable
    @SerialName("run")
    data class Run(val n: Int) : BlockTab
}

/** 가운데 열 탭 단축키 동작. 실제 키와의 대응은 화면에서 정한다. */
enum class TabKey { CLOSE, NEXT, PREVIOUS, PAGE }

/** 탭을 여는 블록 종류. 나머지 종류는 본문 흐름에만 보인다. */
val TAB_BLOCK_TYPES = setOf(BlockType.DOC, BlockType.DATA)

/**
 * 한 페이지의 탭 세트. 첫 탭 "페이지"는 늘 있고 닫을 수 없어서 [tabs]에 넣지 않는다.
 *
 * @property tabs 페이지 탭 뒤에 연 순서대로의 탭.
 * @property active 활성 탭. null이면 페이지 탭.
 */
@Serializable
data class TabSet(val tabs: List<BlockTab> = emptyList(), val active: BlockTab? = null) {

    /** 탭을 열고 활성으로 한다. 이미 열려 있으면 그 탭으로 옮기기만 한다. */
    fun open(tab: BlockTab): TabSet = if (tab in tabs) {
        copy(active = tab)
    } else {
        TabSet(tabs + tab, tab)
    }

    /** 활성 탭을 바꾼다. null은 페이지 탭. 열려 있지 않은 탭이면 그대로 둔다. */
    fun activate(tab: BlockTab?): TabSet =
        if (tab == null || tab in tabs) copy(active = tab) else this

    /** 탭을 닫는다. 활성 탭을 닫으면 그 자리의 다음 탭, 없으면 앞 탭, 없으면 페이지 탭이 활성이다. */
    fun close(tab: BlockTab): TabSet {
        val index = tabs.indexOf(tab)
        if (index < 0) return this
        val rest = tabs - tab
        val next = if (active == tab) rest.getOrNull(index) ?: rest.getOrNull(index - 1) else active
        return TabSet(rest, next)
    }

    /** 활성 탭을 닫는다. 페이지 탭은 닫지 않는다. */
    fun closeActive(): TabSet = active?.let(::close) ?: this

    /** 다음 탭으로. 끝에서는 페이지 탭으로 돈다. */
    fun next(): TabSet = step(+1)

    /** 앞 탭으로. 페이지 탭에서는 마지막 탭으로 돈다. */
    fun previous(): TabSet = step(-1)

    /** 페이지에 없는 블록·run의 탭을 닫는다. */
    fun retainIn(page: PageDetail): TabSet {
        val blocks = page.blocks.filter {
            it.type in TAB_BLOCK_TYPES
        }.mapTo(mutableSetOf()) { it.id }
        val runs = page.runs.mapTo(mutableSetOf()) { it.n }
        val gone = tabs.filterNot {
            when (it) {
                is BlockTab.Block -> it.id in blocks
                is BlockTab.Run -> it.n in runs
            }
        }
        return gone.fold(this) { set, tab -> set.close(tab) }
    }

    private fun step(delta: Int): TabSet {
        val order = listOf<BlockTab?>(null) + tabs
        val index = order.indexOf(active).coerceAtLeast(0)
        return copy(active = order[(index + delta).mod(order.size)])
    }
}

/** 흐름 항목을 클릭했을 때 열 탭. 탭으로 열지 않는 항목이면 null. */
fun tabFor(item: FlowItem): BlockTab? = when (item) {
    is FlowItem.Block -> item.header.takeIf { it.type in TAB_BLOCK_TYPES }?.let {
        BlockTab.Block(it.id)
    }

    is FlowItem.Run -> BlockTab.Run(item.record.n)

    is FlowItem.Pending -> null
}

/** 탭 이름. 블록은 제목, 없으면 파일, 없으면 id. run은 `run N`. */
fun tabName(tab: BlockTab, page: PageDetail): String = when (tab) {
    is BlockTab.Block -> page.blocks.firstOrNull { it.id == tab.id }?.displayName ?: tab.id
    is BlockTab.Run -> "run ${tab.n}"
}

/** 블록을 부르는 이름. */
val BlockHeader.displayName: String get() = title ?: file?.substringAfterLast('/') ?: id

/**
 * 입력창이 보낼 곳.
 *
 * @property block 대상 블록 id. null이면 페이지.
 * @property blockName 대상 블록의 이름. 입력창에 "[이름]에게"로 보인다.
 */
data class SendTarget(val page: String, val block: String? = null, val blockName: String? = null)

/**
 * 활성 탭에 맞는 입력창 대상. 블록 탭이면 그 블록, 페이지 탭이면 페이지다. run은 블록이 아니라서
 * run 탭에서는 페이지에게 보낸다.
 */
fun sendTarget(page: PageDetail, tabs: TabSet): SendTarget {
    val block = (tabs.active as? BlockTab.Block)
        ?.let { tab -> page.blocks.firstOrNull { it.id == tab.id } }
        ?: return SendTarget(page.id)
    return SendTarget(page.id, block.id, block.displayName)
}
