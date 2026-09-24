package madang.shared.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay
import madang.api.model.RunStreamEvent
import madang.shared.main.ActiveRun
import madang.shared.main.ComposerState
import madang.shared.main.MainState
import madang.shared.main.OpenPage
import madang.shared.main.RunActivity
import madang.shared.main.Sidebar
import madang.shared.main.pageMarkdown
import madang.shared.main.pageRuns

/** 가운데 열 조작. */
class PageActions(
    val tabs: TabActions,
    val cancelRun: () -> Unit,
    val back: (() -> Unit)?,
    val toggleMemory: () -> Unit,
    val openDiff: () -> Unit,
    val showUnknownFiles: () -> Unit,
    val answer: (String) -> Unit,
    val undo: () -> Unit,
    val rerun: () -> Unit,
    val composer: ComposerActions,
    val sidebar: SidebarActions
)

/**
 * 가운데 열: 위에 탭 줄, 가운데 활성 탭 내용, 아래 입력창 하나. 첫 탭 "페이지"는 렌더러가 그린
 * 문서 흐름이고, 흐름에서 블록·실행의 "열기"를 누르면 그 종류의 탭이 열린다. 사이드바가 열리면
 * 오른쪽에 붙는다.
 */
@Composable
fun PageColumn(
    state: MainState,
    composer: ComposerState,
    side: SidebarStates,
    actions: PageActions,
    modifier: Modifier
) {
    val sidebar: Sidebar = state.sidebar
    Row(modifier = modifier) {
        CenterColumn(state, composer, actions, Modifier.weight(1f).fillMaxHeight())
        if (sidebar.open) {
            VerticalDivider()
            RightSidebar(
                state,
                side,
                actions.sidebar,
                Modifier.width(SIDEBAR_WIDTH).fillMaxHeight()
            )
        }
    }
}

@Composable
private fun CenterColumn(
    state: MainState,
    composer: ComposerState,
    actions: PageActions,
    modifier: Modifier
) {
    val strings = LocalStrings.current.navigator
    val open = state.page
    Column(modifier = modifier) {
        if (open == null) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                if (state.selectedPage != null) {
                    CircularProgressIndicator()
                } else {
                    Text(strings.noPageSelected, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            return@Column
        }
        TabBar(open.detail, state.tabs, actions.tabs, actions.back)
        HorizontalDivider()
        val content = Modifier.weight(1f).fillMaxWidth()
        when (val tab = state.tabs.active) {
            null -> PageTab(state, open, actions, content)
            else -> CenterTabContent(open, tab, state.pageFolder, actions.tabs, content)
        }
        HorizontalDivider()
        ComposerBar(composer, actions.composer)
    }
}

/**
 * 페이지 탭: 제목과 상태, 미등록 파일 띠, 사람 결정·묻는 블록 카드, 렌더러가 그린 블록 흐름(page.md),
 * 끝에 진행 중인 run 카드 또는 마지막 결과 블록(머지·게시 상태, 되돌리기, 다시 실행).
 */
@Composable
private fun PageTab(state: MainState, open: OpenPage, actions: PageActions, modifier: Modifier) {
    val strings = LocalStrings.current.navigator
    val page = open.detail
    Column(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 8.dp, end = 12.dp, top = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(modifier = Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    page.title,
                    style = MaterialTheme.typography.headlineSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(start = 8.dp).weight(1f, fill = false)
                )
                StatusChip(page.status, Modifier.padding(start = 10.dp))
            }
            TextButton(onClick = actions.openDiff) {
                Text(LocalStrings.current.tabs.openDiff)
            }
            TextButton(onClick = actions.toggleMemory) {
                Text(LocalStrings.current.page.memory)
            }
        }
        if (page.tags.isNotEmpty()) {
            Text(
                page.tags.joinToString(" ") { "#$it" },
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.tertiary,
                modifier = Modifier.padding(start = 16.dp)
            )
        }
        if (page.unknownFiles.isNotEmpty()) {
            UnknownFilesBand(page.unknownFiles.size, actions.showUnknownFiles)
        }
        page.waiting?.let { waiting ->
            val answered = waiting.decision?.id?.let { it == open.answered } == true
            DecisionCard(waiting, answered, actions.answer)
        }
        HorizontalDivider(modifier = Modifier.padding(top = 8.dp))
        val markdown = remember(open) { pageMarkdown(open, open.source) }
        val runs = remember(page.runs, strings) { pageRuns(page.runs) { runSummary(it, strings) } }
        // 페이지마다 새 화면이라 새로 연 페이지는 맨 위부터, 같은 페이지는 새 블록을 따라간다.
        key(page.id) {
            RenderedDocument(
                markdown,
                state.pageFolder,
                actions.tabs.documents,
                Modifier.weight(1f).fillMaxWidth(),
                follow = true,
                runs = runs
            )
        }
        val active = state.activeRuns[page.id]
        val outcome = open.outcome
        if (active != null) {
            Box(modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp)) {
                RunProgressCard(active, actions.cancelRun)
            }
        } else if (outcome != null) {
            ResultBar(
                outcome,
                open.undoing,
                open.undoResult,
                actions.undo,
                actions.rerun,
                Modifier.padding(horizontal = 24.dp, vertical = 8.dp)
            )
        }
    }
}

/** 진행 중인 run: 도구/모델, 경과 시간, 마지막 이벤트 요약, 취소. */
@Composable
private fun RunProgressCard(run: ActiveRun, onCancel: () -> Unit) {
    val strings = LocalStrings.current.navigator
    var elapsed by remember(run.n) { mutableStateOf(run.startedAt.elapsedNow().inWholeSeconds) }
    LaunchedEffect(run.n) {
        while (true) {
            elapsed = run.startedAt.elapsedNow().inWholeSeconds
            delay(1.seconds)
        }
    }
    Row(
        modifier = Modifier.fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp))
            .padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        CircularProgressIndicator(
            modifier = Modifier.padding(end = 10.dp).size(16.dp),
            strokeWidth = 2.dp
        )
        RunnerChip("${run.runner}/${run.model}")
        Column(modifier = Modifier.padding(start = 10.dp).weight(1f)) {
            Text(
                "${strings.running} · ${strings.seconds(elapsed)}",
                style = MaterialTheme.typography.labelMedium
            )
            Text(
                activityText(run.last, strings),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        TextButton(onClick = onCancel) { Text(strings.cancelRun) }
    }
}

/** run의 마지막 이벤트를 한 줄로. */
fun activityText(activity: RunActivity, strings: NavigatorStrings): String = when (activity) {
    RunActivity.Started -> strings.runStarted
    is RunActivity.Assembled -> strings.runAssembled(formatTokens(activity.totalEstimate))
    is RunActivity.Fallback -> strings.runFallback(activity.from, activity.to)
    is RunActivity.Progress -> progressText(activity.event, strings)
}

private fun progressText(event: RunStreamEvent, strings: NavigatorStrings): String =
    when (event.type) {
        RunStreamEvent.Type.TEXT -> strings.runText

        RunStreamEvent.Type.TOOL_CALL ->
            strings.runToolCall(listOfNotNull(event.name, event.summary).joinToString(" "))

        RunStreamEvent.Type.TOOL_RESULT -> strings.runToolResult

        RunStreamEvent.Type.FILE_CHANGED -> strings.runFileChanged(event.path.orEmpty())

        RunStreamEvent.Type.USAGE -> strings.runUsage

        RunStreamEvent.Type.DONE -> strings.runDone

        RunStreamEvent.Type.ERROR -> strings.runError(event.message.orEmpty())
    }

private val SIDEBAR_WIDTH = 420.dp
