package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay
import madang.api.model.RunStreamEvent
import madang.shared.main.ActiveRun
import madang.shared.main.FlowItem
import madang.shared.main.MainState
import madang.shared.main.RunActivity
import madang.shared.main.foldedKeys
import madang.shared.main.isFoldable
import madang.shared.main.pageFlow

/** 3열 조작. */
class PageActions(
    val toggleExpandAll: () -> Unit,
    val toggleFold: (String) -> Unit,
    val cancelRun: () -> Unit,
    val back: (() -> Unit)?
)

/** 3열: 제목과 상태, 미등록 파일 띠, 블록 흐름, 끝에 진행 중인 run 카드. */
@Composable
fun PageColumn(state: MainState, actions: PageActions, modifier: Modifier) {
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
        val page = open.detail
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 8.dp, end = 12.dp, top = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            actions.back?.let {
                ToolbarIcon(Icons.AutoMirrored.Outlined.ArrowBack, strings.back, it)
            }
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
            TextButton(onClick = actions.toggleExpandAll) {
                Text(if (state.expandAll) strings.foldByRule else strings.expandAll)
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
        if (page.unknownFiles.isNotEmpty()) UnknownFilesBand(page.unknownFiles.size)
        HorizontalDivider(modifier = Modifier.padding(top = 8.dp))
        val items = pageFlow(page)
        val folded = foldedKeys(items, state.expandAll, state.toggled)
        val run = state.activeRuns[page.id]
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = 24.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            items(items, key = { it.key }) { item ->
                val isFolded = item.key in folded
                val toggle = { if (isFoldable(item)) actions.toggleFold(item.key) }
                when (item) {
                    is FlowItem.Block ->
                        BlockItem(item.header, open.contents[item.header.id], isFolded, toggle)

                    is FlowItem.Run -> RunItem(item.record, isFolded, toggle)
                }
            }
            if (run != null) {
                item(key = "active-run") { RunProgressCard(run, actions.cancelRun) }
            }
        }
    }
}

@Composable
private fun UnknownFilesBand(count: Int) {
    Text(
        LocalStrings.current.navigator.unknownFiles(count),
        style = MaterialTheme.typography.labelMedium,
        color = Color(0xFF713F12),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .background(Color(0xFFFEF3C7), RoundedCornerShape(6.dp))
            .padding(horizontal = 12.dp, vertical = 6.dp)
    )
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
