package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.Article
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Code
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Difference
import androidx.compose.material.icons.outlined.PlayCircleOutline
import androidx.compose.material.icons.outlined.Public
import androidx.compose.material.icons.outlined.TableChart
import androidx.compose.material.icons.outlined.Terminal
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.PageDetail
import madang.api.model.RunRecord
import madang.api.model.RunStreamEvent
import madang.shared.main.CenterTab
import madang.shared.main.Load
import madang.shared.main.OpenPage
import madang.shared.main.TabKind
import madang.shared.main.TabSet
import madang.shared.main.dataFormatOf
import madang.shared.main.isCodeView
import madang.shared.main.kindOf
import madang.shared.main.tabName

/**
 * 탭 조작.
 *
 * @property activate 탭을 고른다. null은 페이지 탭.
 * @property drawerOpen 탭 안 오른쪽 서랍이 펼쳐져 있다. 모든 블록 탭이 함께 쓴다.
 * @property openExternally 파일이나 URL을 운영체제의 기본 앱으로 연다.
 * @property onEditing 원문 편집기에 포커스가 들어오고 나간다(단축키를 끄고 켠다).
 */
class TabActions(
    val activate: (CenterTab?) -> Unit,
    val close: (CenterTab) -> Unit,
    val drawerOpen: Boolean,
    val toggleDrawer: () -> Unit,
    val data: DataActions = DataActions(),
    val openExternally: (String) -> Unit = {},
    val reloadDiff: () -> Unit = {},
    val onEditing: (Boolean) -> Unit = {}
)

/** 데이터 탭의 원문 편집. 블록 id로 부른다. */
class DataActions(
    val edit: (String, String) -> Unit = { _, _ -> },
    val save: (String) -> Unit = {},
    val discard: (String) -> Unit = {}
)

/** 탭 줄. 첫 탭 "페이지"는 닫기 단추가 없다. 활성 탭 위에 색 막대가 붙는다. */
@Composable
fun TabBar(page: PageDetail, tabs: TabSet, actions: TabActions, back: (() -> Unit)?) {
    val strings = LocalStrings.current
    Row(
        modifier = Modifier.fillMaxWidth().height(TAB_HEIGHT).padding(start = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        back?.let { ToolbarIcon(Icons.AutoMirrored.Outlined.ArrowBack, strings.navigator.back, it) }
        Row(modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState())) {
            TabHeader(
                Icons.AutoMirrored.Outlined.Article,
                strings.tabs.pageTab,
                tabs.active == null,
                onClick = { actions.activate(null) },
                onClose = null
            )
            for (tab in tabs.tabs) {
                TabHeader(
                    tabIcon(tab, page),
                    tabName(tab, page),
                    tabs.active == tab,
                    onClick = { actions.activate(tab) },
                    onClose = { actions.close(tab) }
                )
            }
        }
    }
}

@Composable
private fun TabHeader(
    icon: ImageVector,
    name: String,
    active: Boolean,
    onClick: () -> Unit,
    onClose: (() -> Unit)?
) {
    val colors = MaterialTheme.colorScheme
    Column(
        modifier = Modifier.fillMaxHeight().width(IntrinsicSize.Max).widthIn(max = TAB_MAX_WIDTH)
            .background(if (active) colors.surface else colors.surfaceVariant.copy(alpha = 0.4f))
            .clickable(onClick = onClick)
    ) {
        Box(
            Modifier.fillMaxWidth().height(ACTIVE_BAR)
                .background(if (active) colors.primary else Color.Transparent)
        )
        Row(
            modifier = Modifier.weight(1f)
                .padding(start = 10.dp, end = if (onClose != null) 2.dp else 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(15.dp),
                tint = if (active) colors.primary else colors.onSurfaceVariant
            )
            Text(
                name,
                style = MaterialTheme.typography.labelLarge,
                color = if (active) colors.onSurface else colors.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 6.dp).weight(1f, fill = false)
            )
            onClose?.let {
                ToolbarIcon(Icons.Outlined.Close, LocalStrings.current.tabs.closeTab, it)
            }
        }
    }
    VerticalDivider()
}

/** 탭 머리의 아이콘. 탭 종류를 따르고, run 탭과 코드 보기만 따로 구분한다. */
private fun tabIcon(tab: CenterTab, page: PageDetail): ImageVector = when {
    tab is CenterTab.Run -> Icons.Outlined.PlayCircleOutline

    tab is CenterTab.File && isCodeView(tab.path) -> Icons.Outlined.Code

    else -> when (kindOf(tab, page)) {
        TabKind.DOCUMENT -> Icons.Outlined.Description
        TabKind.DATA -> Icons.Outlined.TableChart
        TabKind.BROWSER -> Icons.Outlined.Public
        TabKind.DIFF -> Icons.Outlined.Difference
        TabKind.TERMINAL -> Icons.Outlined.Terminal
        TabKind.CHAT -> Icons.AutoMirrored.Outlined.Chat
    }
}

/** 페이지 탭이 아닌 탭의 내용. 탭 종류([kindOf])대로 그린다. */
@Composable
fun CenterTabContent(open: OpenPage, tab: CenterTab, actions: TabActions, modifier: Modifier) {
    when (tab) {
        is CenterTab.Block -> BlockTabContent(open, tab, actions, modifier)

        is CenterTab.Run -> {
            val run = open.detail.runs.firstOrNull { it.n == tab.n } ?: return
            RunTab(open.detail, run, open.runEvents[run.n], actions, modifier)
        }

        is CenterTab.Browser -> BrowserTab(tab.url, actions, modifier)

        CenterTab.Diff -> DiffTab(open.diff, actions, modifier)

        is CenterTab.File -> FileTabContent(tab.path, open.files[tab.path], actions, modifier)
    }
}

/** 블록 탭: 블록 파일이 데이터면 데이터 탭(원문 저장 가능), 아니면 문서 탭. */
@Composable
private fun BlockTabContent(
    open: OpenPage,
    tab: CenterTab.Block,
    actions: TabActions,
    modifier: Modifier
) {
    val block = open.detail.blocks.firstOrNull { it.id == tab.id } ?: return
    val content = open.contents[block.id]
    val format = block.file?.let(::dataFormatOf)
    if (kindOf(tab, open.detail) == TabKind.DATA && format != null) {
        DataTab(
            key = block.id,
            content = content,
            format = format,
            edit = DataEdit(block.id, open.drafts[block.id]),
            actions = actions,
            modifier = modifier
        ) { BlockFacts(block, content) }
    } else {
        DocTab(block.id, content, actions, modifier) { BlockFacts(block, content) }
    }
}

/**
 * 작업 폴더 파일 탭. 데이터 파일은 데이터 탭, `.md`는 문서 탭, 그 밖은 문서 탭의 코드 보기다. 모두
 * 읽기만 한다.
 */
@Composable
private fun FileTabContent(
    path: String,
    loaded: Load<String>?,
    actions: TabActions,
    modifier: Modifier
) {
    val strings = LocalStrings.current.tabs
    val content = (loaded as? Load.Ready)?.value
    if (loaded is Load.Failed) {
        TabFrame(
            modifier,
            actions,
            main = { Placeholder(strings.cannotRead(loaded.message)) },
            drawer = { FileFacts(path, null, actions) }
        )
        return
    }
    val format = dataFormatOf(path)
    when {
        format != null -> DataTab(
            key = path,
            content = content,
            format = format,
            edit = null,
            actions = actions,
            modifier = modifier
        ) { FileFacts(path, content, actions) }

        isCodeView(path) -> CodeTab(path, content, actions, modifier)

        else -> DocTab(path, content, actions, modifier) { FileFacts(path, content, actions) }
    }
}

/** 문서 탭. 서랍에서 미리보기와 원본을 바꾼다. */
@Composable
private fun DocTab(
    key: String,
    content: String?,
    actions: TabActions,
    modifier: Modifier,
    facts: @Composable ColumnScope.() -> Unit
) {
    val strings = LocalStrings.current.tabs
    var source by remember(key) { mutableStateOf(false) }
    TabFrame(
        modifier,
        actions,
        main = {
            when {
                content == null -> Placeholder(strings.loading)
                source -> SourceText(content)
                else -> PageMarkdown(content)
            }
        },
        drawer = {
            ModeToggle(strings.preview, strings.source, source) { source = it }
            facts()
        }
    )
}

/** 문서 탭의 코드 보기. 줄 번호와 원문만 보이고 고치지 않는다. 고치려면 외부 편집기로 연다. */
@Composable
private fun CodeTab(path: String, content: String?, actions: TabActions, modifier: Modifier) {
    val strings = LocalStrings.current.tabs
    TabFrame(
        modifier,
        actions,
        main = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    strings.codeView,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f)
                )
                TextButton(onClick = { actions.openExternally(path) }) {
                    Text(strings.openInEditor)
                }
            }
            if (content == null) Placeholder(strings.loading) else NumberedSource(content)
        },
        drawer = { FileFacts(path, content, actions) }
    )
}

/** 줄 번호를 붙인 원문. 줄바꿈하지 않고 가로로 스크롤한다. */
@Composable
private fun NumberedSource(content: String) {
    val lines = content.lines()
    val width = lines.size.toString().length
    SelectionContainer {
        Column(modifier = Modifier.horizontalScroll(rememberScrollState())) {
            lines.forEachIndexed { index, line ->
                Row {
                    Text(
                        (index + 1).toString().padStart(width),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.outline,
                        modifier = Modifier.padding(end = 12.dp)
                    )
                    Text(
                        line,
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        softWrap = false
                    )
                }
            }
        }
    }
}

@Composable
private fun FileFacts(path: String, content: String?, actions: TabActions) {
    val strings = LocalStrings.current.tabs
    DrawerFact(strings.file, null)
    MonoLine(path)
    content?.let { DrawerFact(strings.lines(it.lines().size), null) }
    DrawerFact(strings.readOnly, null)
    TextButton(onClick = { actions.openExternally(path) }) { Text(strings.openInEditor) }
}

/**
 * run 탭. 본문에는 이 run을 일으킨 요청과 run이 남긴 메시지를, 서랍에는 입력 구성·사용량·바뀐
 * 파일·이벤트 로그를 보인다.
 */
@Composable
private fun RunTab(
    page: PageDetail,
    run: RunRecord,
    events: List<RunStreamEvent>?,
    actions: TabActions,
    modifier: Modifier
) {
    val strings = LocalStrings.current
    val messages = page.blocks.filter {
        it.type == BlockType.MESSAGE && (it.run == run.n || it.id == run.trigger?.message)
    }
    TabFrame(
        modifier,
        actions,
        main = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RunnerChip("${run.runner.orEmpty()}/${run.model.orEmpty()}")
                Text(
                    runSummary(run, strings.navigator),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(start = 8.dp).weight(1f)
                )
                run.resultStatus?.let {
                    Text(
                        it.value,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            }
            Text(
                strings.tabs.runRequest,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 16.dp, bottom = 8.dp)
            )
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                messages.forEach { BlockItem(it, null, folded = false, onToggle = {}) }
            }
        },
        drawer = { RunDrawer(run, events) }
    )
}

@Composable
private fun ColumnScope.RunDrawer(run: RunRecord, events: List<RunStreamEvent>?) {
    val strings = LocalStrings.current.tabs
    DrawerSection(strings.inputParts)
    val input = run.input
    if (input == null) {
        DrawerFact(strings.none, null)
    } else {
        val parts = input.parts
        listOf(
            "system" to parts.systemEst,
            "profile" to parts.profile,
            "brief" to parts.brief,
            "ledger" to parts.ledger,
            "contract" to parts.contract,
            "target" to parts.target,
            "request" to parts.request
        ).forEach { (name, tokens) -> DrawerFact(name, formatTokens(tokens)) }
        DrawerFact(strings.inputTotal, formatTokens(input.totalEst))
    }
    DrawerSection(strings.usage)
    DrawerFact(strings.usageInput, formatTokens(run.usage.input))
    DrawerFact(strings.usageCached, formatTokens(run.usage.cached))
    DrawerFact(strings.usageOutput, formatTokens(run.usage.output))
    DrawerSection(strings.changedFiles)
    if (run.changedFiles.isEmpty()) DrawerFact(strings.none, null)
    run.changedFiles.forEach { MonoLine(it) }
    DrawerSection(strings.eventLog)
    when {
        events == null -> DrawerFact(strings.loading, null)
        events.isEmpty() -> DrawerFact(strings.noEvents, null)
        else -> events.forEach { MonoLine(eventLine(it)) }
    }
}

/** 이벤트 한 줄: 종류와 그 종류의 내용. */
fun eventLine(event: RunStreamEvent): String {
    val detail = when (event.type) {
        RunStreamEvent.Type.TEXT, RunStreamEvent.Type.DONE -> event.text

        RunStreamEvent.Type.TOOL_CALL -> listOfNotNull(event.name, event.summary).joinToString(" ")

        RunStreamEvent.Type.TOOL_RESULT -> event.summary

        RunStreamEvent.Type.FILE_CHANGED -> event.path

        RunStreamEvent.Type.USAGE -> event.usage?.let {
            "in ${formatTokens(it.input)} · cached ${formatTokens(it.cached)} · " +
                "out ${formatTokens(it.output)}"
        }

        RunStreamEvent.Type.ERROR -> event.message
    }
    return listOfNotNull(event.type.value, detail).joinToString("  ")
}

/** 블록 탭의 틀: 위 머리줄(서랍 토글), 왼쪽 본문, 오른쪽 서랍. */
@Composable
internal fun TabFrame(
    modifier: Modifier,
    actions: TabActions,
    main: @Composable ColumnScope.() -> Unit,
    drawer: @Composable ColumnScope.() -> Unit
) {
    val strings = LocalStrings.current.tabs
    Row(modifier = modifier) {
        Column(modifier = Modifier.weight(1f).fillMaxHeight()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.End
            ) {
                TextButton(onClick = actions.toggleDrawer) {
                    Text(if (actions.drawerOpen) strings.hideDrawer else strings.showDrawer)
                }
            }
            Column(
                modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                    .padding(start = 24.dp, end = 24.dp, bottom = 16.dp),
                content = main
            )
        }
        if (actions.drawerOpen) {
            VerticalDivider()
            Column(
                modifier = Modifier.width(DRAWER_WIDTH).fillMaxHeight()
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
                content = drawer
            )
        }
    }
}

/** 두 보기 중 하나를 고르는 칩 한 쌍. [second]가 true면 두 번째가 골라져 있다. */
@Composable
private fun ModeToggle(
    first: String,
    secondLabel: String,
    second: Boolean,
    pick: (Boolean) -> Unit
) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        FilterChip(selected = !second, onClick = { pick(false) }, label = { Text(first) })
        FilterChip(selected = second, onClick = { pick(true) }, label = { Text(secondLabel) })
    }
    HorizontalDivider(modifier = Modifier.padding(vertical = 6.dp))
}

@Composable
internal fun BlockFacts(block: BlockHeader, content: String?) {
    val strings = LocalStrings.current.tabs
    block.file?.let { DrawerFact(strings.file, it) }
    block.createdBy?.let { DrawerFact(strings.createdBy, it) }
    content?.let { DrawerFact(strings.lines(it.lines().size), null) }
}

@Composable
internal fun DrawerSection(title: String) {
    Text(
        title,
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier.padding(top = 10.dp, bottom = 2.dp)
    )
}

/** 서랍의 한 줄. [value]가 없으면 [label]만 보인다. */
@Composable
internal fun DrawerFact(label: String, value: String?) {
    Row(modifier = Modifier.fillMaxWidth()) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f)
        )
        value?.let { Text(it, style = MaterialTheme.typography.labelMedium) }
    }
}

@Composable
internal fun MonoLine(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        fontFamily = FontFamily.Monospace,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )
}

@Composable
internal fun SourceText(content: String) {
    SelectionContainer {
        Text(
            content,
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace
        )
    }
}

@Composable
internal fun Placeholder(text: String) {
    Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

private val TAB_HEIGHT = 36.dp
private val TAB_MAX_WIDTH = 220.dp
private val ACTIVE_BAR = 2.dp
private val DRAWER_WIDTH = 300.dp
