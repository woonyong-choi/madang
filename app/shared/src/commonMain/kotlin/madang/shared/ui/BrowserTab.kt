package madang.shared.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import madang.shared.BrowserStatus
import madang.shared.LocalBrowserEngine

/**
 * 브라우저 탭. 위에 주소·새로 고침·외부 브라우저로 열기, 아래에 웹 화면. 엔진이 준비되지 않았으면
 * 처음 보일 때 준비를 시작하고(첫 실행은 번들 내려받기) 진행을 보인다.
 */
@Composable
fun BrowserTab(url: String, actions: TabActions, modifier: Modifier) {
    val strings = LocalStrings.current.tabs
    val engine = LocalBrowserEngine.current
    val status by engine.status.collectAsState()
    var reload by remember(url) { mutableIntStateOf(0) }
    LaunchedEffect(engine) { engine.prepare() }
    Column(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            SelectionContainer(modifier = Modifier.weight(1f)) {
                Text(
                    url,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            TextButton(onClick = { reload++ }, enabled = status == BrowserStatus.Ready) {
                Text(strings.reload)
            }
            TextButton(onClick = { actions.openExternally(url) }) { Text(strings.openInBrowser) }
        }
        HorizontalDivider()
        val body = Modifier.weight(1f).fillMaxWidth()
        when (val current = status) {
            BrowserStatus.Ready -> engine.Page(url, reload, body)
            else -> EngineNotice(current, body)
        }
    }
}

/** 엔진이 준비되지 않았을 때 가운데에 보이는 상태와 진행. 실패했으면 "다시 받기"를 둔다. */
@Composable
internal fun EngineNotice(status: BrowserStatus, modifier: Modifier) {
    val strings = LocalStrings.current.tabs
    val engine = LocalBrowserEngine.current
    Box(modifier = modifier.padding(24.dp), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            when (status) {
                is BrowserStatus.Downloading -> {
                    val percent = status.percent.takeIf { it >= 0f }
                    NoticeText(strings.browserDownloading(percent?.toInt()))
                    if (percent != null) {
                        LinearProgressIndicator(
                            progress = { percent / FULL },
                            modifier = Modifier.width(PROGRESS_WIDTH)
                        )
                    } else {
                        LinearProgressIndicator(modifier = Modifier.width(PROGRESS_WIDTH))
                    }
                    NoticeText(strings.browserFirstRun, secondary = true)
                }

                BrowserStatus.Idle, BrowserStatus.Installing -> {
                    CircularProgressIndicator()
                    NoticeText(strings.browserInstalling)
                }

                BrowserStatus.RestartRequired -> NoticeText(strings.browserRestart)

                is BrowserStatus.Failed -> {
                    NoticeText(strings.browserFailed(status.message))
                    TextButton(onClick = engine::reinstall) { Text(strings.reinstallEngine) }
                }

                BrowserStatus.Unavailable -> NoticeText(strings.browserUnavailable)

                BrowserStatus.Ready -> Unit
            }
        }
    }
}

@Composable
private fun NoticeText(text: String, secondary: Boolean = false) {
    Text(
        text,
        style = if (secondary) {
            MaterialTheme.typography.labelMedium
        } else {
            MaterialTheme.typography.bodyMedium
        },
        color = if (secondary) {
            MaterialTheme.colorScheme.onSurfaceVariant
        } else {
            MaterialTheme.colorScheme.onSurface
        },
        textAlign = TextAlign.Center
    )
}

private const val FULL = 100f
private val PROGRESS_WIDTH = 280.dp
