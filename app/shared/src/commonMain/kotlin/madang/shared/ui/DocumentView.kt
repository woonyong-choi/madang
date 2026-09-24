package madang.shared.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp
import madang.shared.BrowserStatus
import madang.shared.LocalBrowserEngine
import madang.shared.main.AppTokens
import madang.shared.main.DocumentContext
import madang.shared.main.DocumentPayload
import madang.shared.main.DocumentRequest
import madang.shared.main.RunEntry
import madang.shared.main.ViewEntry
import madang.shared.main.fileUrl
import madang.shared.main.parseDocumentRequest

/**
 * 문서 탭의 링크와 view 펜스.
 *
 * @property open 문서 안 링크 요청을 연다. 둘째 인자는 그 문서의 폴더다.
 * @property views 문서의 view 펜스를 렌더러 context로 푼다(원문, 문서 폴더).
 */
class DocumentActions(
    val open: (DocumentRequest, String?) -> Unit = { _, _ -> },
    val views: suspend (String, String?) -> Map<String, ViewEntry> = { _, _ -> emptyMap() }
)

/**
 * [markdown]을 렌더러로 그린다. view 펜스를 먼저 풀고, 풀기 전에는 비워 둔다. 원문이 바뀌어
 * 다시 푸는 동안에는 앞서 푼 것을 쓴다.
 *
 * @param dir 문서 폴더. 상대 링크·이미지와 view 펜스 `data=`의 기준이다.
 * @param follow 블록이 늘면 끝으로 스크롤한다(페이지 흐름).
 * @param runs 실행 기록. 렌더러가 접힌 실행 블록으로 그린다.
 */
@Composable
fun RenderedDocument(
    markdown: String,
    dir: String?,
    actions: DocumentActions,
    modifier: Modifier,
    follow: Boolean = false,
    runs: List<RunEntry> = emptyList()
) {
    val views by produceState<Map<String, ViewEntry>?>(null, markdown, dir) {
        value = actions.views(markdown, dir)
    }
    val resolved = views ?: return
    val document = DocumentPayload(
        markdown = markdown,
        context = DocumentContext(views = resolved, runs = runs),
        base = dir?.let { fileUrl(it) + "/" },
        follow = follow
    )
    DocumentView(document, { actions.open(it, dir) }, modifier)
}

/**
 * 문서 탭 본문. 렌더러(`templates/_runtime`)가 WebView 안에서 [document]를 그린다. 게시 사이트와
 * 같은 렌더러라 로컬과 웹의 모양이 같다. 앱 테마의 토큰 다섯 개를 context에 넣고, 문서 안 링크는
 * [onRequest]로 받는다. 엔진이 준비 중이면 진행을, 엔진이 없는 플랫폼이면 원문을 보인다. 엔진을
 * 준비하지 못했으면 이유와 "다시 받기" 아래에 원문을 읽기 전용으로 보인다(렌더러를 따로 두지 않는다).
 */
@Composable
fun DocumentView(
    document: DocumentPayload,
    onRequest: (DocumentRequest) -> Unit,
    modifier: Modifier
) {
    val engine = LocalBrowserEngine.current
    val status by engine.status.collectAsState()
    LaunchedEffect(engine) { engine.prepare() }
    val tokens = appTokens(MaterialTheme.colorScheme)
    val payload = remember(document, tokens) {
        document.copy(context = document.context.copy(tokens = tokens)).toJson()
    }
    val handler by rememberUpdatedState(onRequest)
    when (status) {
        BrowserStatus.Ready -> engine.Document(
            payload,
            { url -> parseDocumentRequest(url)?.let(handler) },
            modifier
        )

        BrowserStatus.Unavailable -> RawDocument(document.markdown, modifier)

        is BrowserStatus.Failed -> Column(modifier) {
            EngineNotice(status, Modifier.fillMaxWidth())
            RawDocument(document.markdown, Modifier.weight(1f).fillMaxWidth())
        }

        else -> EngineNotice(status, modifier)
    }
}

/** 원문 md를 읽기 전용으로. 웹 엔진이 없거나 준비하지 못했을 때 쓴다. */
@Composable
private fun RawDocument(markdown: String, modifier: Modifier) {
    Box(modifier.verticalScroll(rememberScrollState()).padding(horizontal = 24.dp)) {
        SourceText(markdown)
    }
}

/** 앱 테마를 렌더러 토큰으로. 뷰어 iframe과 문서 바탕이 이 값을 따른다. */
fun appTokens(colors: ColorScheme): AppTokens = AppTokens(
    bg = cssColor(colors.surface),
    text = cssColor(colors.onSurface),
    accent = cssColor(colors.primary),
    font = APP_FONT,
    radius = APP_RADIUS
)

/** 불투명 CSS 색(`#rrggbb`). */
fun cssColor(color: Color): String =
    "#" + (color.toArgb() and RGB_MASK).toString(HEX_RADIX).padStart(RGB_DIGITS, '0')

private const val APP_FONT =
    "-apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Segoe UI', sans-serif"
private const val APP_RADIUS = "8px"
private const val RGB_MASK = 0xffffff
private const val HEX_RADIX = 16
private const val RGB_DIGITS = 6
