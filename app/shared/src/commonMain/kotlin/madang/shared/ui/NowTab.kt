package madang.shared.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.datetime.toLocalDateTime
import madang.api.model.RunInput
import madang.api.model.RunStreamEvent
import madang.api.model.ToolUsage
import madang.api.model.Usage
import madang.api.model.UsageWindow
import madang.shared.main.Load
import madang.shared.main.MainState
import madang.shared.main.NowItem
import madang.shared.main.NowState
import madang.shared.main.RunKey

/** 지금 탭 조작. */
class NowActions(
    val showInput: (NowItem) -> Unit,
    val toggleLog: (NowItem) -> Unit,
    val openPage: (NowItem) -> Unit,
    val refreshUsage: () -> Unit
)

/**
 * 사이드바 지금 탭: 위에 구독 사용량, 아래에 모든 프로젝트의 진행 중·사람 필요·최근 30분 run.
 *
 * 줄을 누르면 그 run의 마지막 호출 입력 구성을, "로그"를 누르면 진행 로그의 마지막 30줄을 펼친다.
 * 두 번 누르면 그 페이지를 연다. 읽지 않은 완료는 굵게 보인다.
 */
@Composable
fun NowTab(main: MainState, state: NowState, actions: NowActions, modifier: Modifier) {
    val strings = LocalStrings.current.side
    val clock = LocalListClock.current
    val items = main.nowItems(clock.now())
    Column(modifier = modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        UsageSection(state.usage, actions.refreshUsage)
        HorizontalDivider(modifier = Modifier.padding(vertical = 10.dp))
        SideHeading(strings.nowTitle)
        if (items.isEmpty()) SideNote(strings.nowEmpty)
        items.forEach { item ->
            val key = item.n?.let { RunKey(item.page, it) }
            NowRow(
                item,
                input = state.input?.takeIf { it.first == key }?.second,
                log = state.log?.takeIf { it.first == key }?.second,
                actions = actions
            )
        }
    }
}

@Composable
private fun UsageSection(usage: Load<Usage>?, onRefresh: () -> Unit) {
    val strings = LocalStrings.current.side
    Row(verticalAlignment = Alignment.CenterVertically) {
        SideHeading(strings.usageTitle, Modifier.weight(1f))
        TextButton(onClick = onRefresh, contentPadding = PaddingValues(horizontal = 6.dp)) {
            Text(strings.reload, style = MaterialTheme.typography.labelSmall)
        }
    }
    when (usage) {
        null, Load.Loading -> SideNote(strings.loading)
        is Load.Failed -> SideError(strings.failed(usage.message))
        is Load.Ready -> usage.value.tools.forEach { ToolUsageRows(it) }
    }
}

/**
 * 도구 하나의 5시간·7일 창. 한도를 알면(core가 비율을 주면) 막대와 비율을, 모르면 쓴 토큰만
 * 보인다. 경고는 core가 준 `warn`만 쓴다.
 */
@Composable
private fun ToolUsageRows(tool: ToolUsage) {
    val strings = LocalStrings.current.side
    Text(
        tool.tool.value,
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier.padding(top = 6.dp)
    )
    if (!tool.available) {
        SideNote(strings.usageNoRecords)
        return
    }
    tool.windows.forEach { window -> UsageWindowRow(window) }
}

@Composable
private fun UsageWindowRow(window: UsageWindow) {
    val strings = LocalStrings.current.side
    val colors = MaterialTheme.colorScheme
    val tint = if (window.warn) colors.error else colors.primary
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Row {
            Text(
                strings.usageWindow(window.name),
                style = MaterialTheme.typography.labelMedium,
                color = colors.onSurfaceVariant,
                modifier = Modifier.weight(1f)
            )
            val used = strings.usageTokens(formatTokens(window.usedTokens))
            val limit = window.limitTokens?.let { " / ${formatTokens(it)}" }.orEmpty()
            val percent = window.percent?.let { " · ${it.toInt()}%" }.orEmpty()
            Text(
                used + limit + percent,
                style = MaterialTheme.typography.labelMedium,
                color = if (window.warn) colors.error else colors.onSurface
            )
        }
        window.percent?.let { percent ->
            LinearProgressIndicator(
                progress = { (percent / FULL_PERCENT).toFloat().coerceIn(0f, 1f) },
                color = tint,
                modifier = Modifier.fillMaxWidth().padding(top = 2.dp)
            )
        }
        if (window.warn) {
            Text(
                strings.usageWarn,
                style = MaterialTheme.typography.labelSmall,
                color = colors.error
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun NowRow(
    item: NowItem,
    input: Load<RunInput?>?,
    log: Load<List<RunStreamEvent>>?,
    actions: NowActions
) {
    val strings = LocalStrings.current.side
    val colors = MaterialTheme.colorScheme
    val selected = input != null
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp)
            .background(
                if (selected) colors.surfaceVariant else colors.surfaceContainerLow,
                RoundedCornerShape(6.dp)
            )
            .combinedClickable(
                onClick = { actions.showInput(item) },
                onDoubleClick = { actions.openPage(item) }
            )
            .padding(horizontal = 8.dp, vertical = 6.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusGlyph(item.glyph, Modifier.padding(end = 8.dp))
            Text(
                item.title,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = if (item.unread) FontWeight.Bold else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f)
            )
            Text(
                timeText(item),
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                detailText(item),
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f).padding(start = 22.dp)
            )
            if (item.n != null) {
                TextButton(
                    onClick = { actions.toggleLog(item) },
                    contentPadding = PaddingValues(horizontal = 6.dp)
                ) {
                    Text(
                        if (log != null) strings.hideLog else strings.showLog,
                        style = MaterialTheme.typography.labelSmall
                    )
                }
            }
        }
        input?.let { InputSection(item, it) }
        log?.let { LogSection(it) }
    }
}

@Composable
private fun InputSection(item: NowItem, input: Load<RunInput?>) {
    val strings = LocalStrings.current.side
    Column(modifier = Modifier.padding(start = 22.dp, top = 4.dp)) {
        Text(strings.inputTitle(item.n ?: 0), style = MaterialTheme.typography.labelMedium)
        when (input) {
            Load.Loading -> SideNote(strings.loading)

            is Load.Failed -> SideError(strings.failed(input.message))

            is Load.Ready -> input.value?.let { InputFacts(it, strings.inputTotal) }
                ?: SideNote(strings.inputNotRecorded)
        }
    }
}

@Composable
private fun LogSection(log: Load<List<RunStreamEvent>>) {
    val strings = LocalStrings.current.side
    Column(
        modifier = Modifier.padding(start = 22.dp, top = 4.dp),
        verticalArrangement = Arrangement.spacedBy(1.dp)
    ) {
        when (log) {
            Load.Loading -> SideNote(strings.loading)

            is Load.Failed -> SideError(strings.failed(log.message))

            is Load.Ready -> if (log.value.isEmpty()) {
                SideNote(strings.noEvents)
            } else {
                log.value.forEach { MonoLine(eventLine(it)) }
            }
        }
    }
}

/** 진행 중이면 마지막 활동, 아니면 runner/모델과 run 번호. */
@Composable
private fun detailText(item: NowItem): String {
    val runner = listOfNotNull(item.runner, item.model).joinToString("/")
    val n = item.n?.let { "run $it" }
    val activity = item.active?.last?.let { activityText(it, LocalStrings.current.navigator) }
    return listOfNotNull(n, runner.ifEmpty { null }, activity).joinToString(" · ")
}

/** 시작하거나 끝난 시각(시:분). */
@Composable
private fun timeText(item: NowItem): String {
    val at = item.at ?: return ""
    val time = at.toLocalDateTime(LocalListClock.current.zone)
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private const val FULL_PERCENT = 100.0
