package madang.shared.main

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageDetail

/**
 * 가운데 열에서 페이지 탭 옆에 여는 탭. 탭은 화면 배치일 뿐이고 닫아도 블록·파일은 남는다. 탭의
 * 종류([TabKind])는 [kindOf]가 정한다.
 */
@Serializable
sealed interface CenterTab {
    /** 페이지 블록(doc·data·view). 종류는 블록 파일의 확장자를 따른다. */
    @Serializable
    @SerialName("block")
    data class Block(val id: String) : CenterTab

    /** run 기록. 페이지 문서의 일부라 문서 탭이다. */
    @Serializable
    @SerialName("run")
    data class Run(val n: Int) : CenterTab

    /** URL 하나를 보이는 브라우저 탭. 로컬 파일은 `file://` URL이다. */
    @Serializable
    @SerialName("browser")
    data class Browser(val url: String) : CenterTab

    /** 페이지 작업 폴더의 git diff. 페이지마다 하나다. */
    @Serializable
    @SerialName("diff")
    data object Diff : CenterTab

    /** 작업 폴더의 파일 하나(절대 경로). 읽기만 한다. */
    @Serializable
    @SerialName("file")
    data class File(val path: String) : CenterTab
}

/** 가운데 열 탭 단축키 동작. 실제 키와의 대응은 화면에서 정한다. */
enum class TabKey { CLOSE, NEXT, PREVIOUS, PAGE }

/** 블록 탭([CenterTab.Block])으로 여는 블록 종류. 내용은 core에서 받는다. */
val TAB_BLOCK_TYPES = setOf(BlockType.DOC, BlockType.DATA, BlockType.VIEW)

/**
 * 한 페이지의 탭 세트. 첫 탭 "페이지"는 늘 있고 닫을 수 없어서 [tabs]에 넣지 않는다.
 *
 * @property tabs 페이지 탭 뒤에 연 순서대로의 탭.
 * @property active 활성 탭. null이면 페이지 탭.
 */
@Serializable
data class TabSet(val tabs: List<CenterTab> = emptyList(), val active: CenterTab? = null) {

    /** 탭을 열고 활성으로 한다. 이미 열려 있으면 그 탭으로 옮기기만 한다. */
    fun open(tab: CenterTab): TabSet = if (tab in tabs) {
        copy(active = tab)
    } else {
        TabSet(tabs + tab, tab)
    }

    /** 활성 탭을 바꾼다. null은 페이지 탭. 열려 있지 않은 탭이면 그대로 둔다. */
    fun activate(tab: CenterTab?): TabSet =
        if (tab == null || tab in tabs) copy(active = tab) else this

    /** 탭을 닫는다. 활성 탭을 닫으면 그 자리의 다음 탭, 없으면 앞 탭, 없으면 페이지 탭이 활성이다. */
    fun close(tab: CenterTab): TabSet {
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

    /** 페이지에 없는 블록·run의 탭을 닫는다. 브라우저·디프·파일 탭은 페이지와 상관없이 둔다. */
    fun retainIn(page: PageDetail): TabSet {
        val blocks = page.blocks.filter {
            it.type in TAB_BLOCK_TYPES
        }.mapTo(mutableSetOf()) { it.id }
        val runs = page.runs.mapTo(mutableSetOf()) { it.n }
        val gone = tabs.filterNot {
            when (it) {
                is CenterTab.Block -> it.id in blocks
                is CenterTab.Run -> it.n in runs
                is CenterTab.Browser, CenterTab.Diff, is CenterTab.File -> true
            }
        }
        return gone.fold(this) { set, tab -> set.close(tab) }
    }

    private fun step(delta: Int): TabSet {
        val order = listOf<CenterTab?>(null) + tabs
        val index = order.indexOf(active).coerceAtLeast(0)
        return copy(active = order[(index + delta).mod(order.size)])
    }
}

/**
 * 흐름 항목을 더블클릭했을 때 여는 것. run은 run 탭, doc·data·view 블록은 블록 탭, 나머지 블록은
 * [openRequestFor]를 따른다. 열 것이 없으면 null.
 */
fun openTargetFor(item: FlowItem): OpenTarget? = when (item) {
    is FlowItem.Block -> if (item.header.type in TAB_BLOCK_TYPES) {
        OpenTarget.Tab(CenterTab.Block(item.header.id))
    } else {
        openRequestFor(item.header)?.let(OpenTarget::Request)
    }

    is FlowItem.Run -> OpenTarget.Tab(CenterTab.Run(item.record.n))

    is FlowItem.Pending -> null
}

/** 흐름 항목이 여는 것. 이미 정해진 탭이거나, 탭을 정하려면 풀어야 하는 요청이다. */
sealed interface OpenTarget {
    data class Tab(val tab: CenterTab) : OpenTarget

    data class Request(val request: OpenRequest) : OpenTarget
}

/**
 * 탭의 종류. 페이지 탭(null)과 run 탭은 문서, 블록 탭과 파일 탭은 파일 확장자, 브라우저·디프 탭은
 * 그 자체다.
 */
fun kindOf(tab: CenterTab?, page: PageDetail): TabKind = when (tab) {
    null, is CenterTab.Run -> TabKind.DOCUMENT

    is CenterTab.Block -> page.blocks.firstOrNull { it.id == tab.id }?.file
        ?.let { tabKindOf(OpenRequest.File(it)) } ?: TabKind.DOCUMENT

    is CenterTab.Browser -> TabKind.BROWSER

    CenterTab.Diff -> TabKind.DIFF

    is CenterTab.File -> tabKindOf(OpenRequest.File(tab.path))
}

/** 탭 이름. 블록은 제목, 없으면 파일, 없으면 id. run은 `run N`. 파일은 파일 이름, URL은 주소. */
fun tabName(tab: CenterTab, page: PageDetail): String = when (tab) {
    is CenterTab.Block -> page.blocks.firstOrNull { it.id == tab.id }?.displayName ?: tab.id
    is CenterTab.Run -> "run ${tab.n}"
    is CenterTab.Browser -> tab.url.substringAfter("://").trimEnd('/')
    CenterTab.Diff -> "diff"
    is CenterTab.File -> tab.path.substringAfterLast('/')
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
    val block = (tabs.active as? CenterTab.Block)
        ?.let { tab -> page.blocks.firstOrNull { it.id == tab.id } }
        ?: return SendTarget(page.id)
    return SendTarget(page.id, block.id, block.displayName)
}
