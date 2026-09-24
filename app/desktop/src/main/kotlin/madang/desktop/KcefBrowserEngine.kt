package madang.desktop

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.awt.SwingPanel
import dev.datlag.kcef.KCEF
import dev.datlag.kcef.KCEFClient
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.max
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import madang.shared.BrowserEngine
import madang.shared.BrowserStatus
import madang.shared.main.fileUrl
import org.cef.browser.CefRendering

/**
 * KCEF(Chromium) 브라우저 엔진.
 *
 * 브라우저 탭이나 문서 탭을 처음 열 때 [prepare]가 불리고, 엔진 번들이 [installDir]에 없으면
 * 내려받아 푼다(첫 실행). 진행은 [status]로 알린다. 캐시는 [installDir] 옆 `kcef-cache`에 둔다.
 * 문서 탭은 [runtime]의 렌더러 호스트를 연다.
 */
class KcefBrowserEngine(private val installDir: File, private val runtime: DocumentRuntime) :
    BrowserEngine {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val started = AtomicBoolean(false)
    private val _status = MutableStateFlow<BrowserStatus>(BrowserStatus.Idle)
    override val status: StateFlow<BrowserStatus> = _status.asStateFlow()

    private val documents = DocumentBridge()
    private val documentCount = AtomicInteger()
    private val client: KCEFClient by lazy {
        KCEF.newClientBlocking().apply {
            addRequestHandler(documents.requests)
            addLoadHandler(documents.loads)
        }
    }
    private val host: String by lazy { fileUrl(runtime.install().absolutePath) }

    override fun prepare() {
        if (!started.compareAndSet(false, true)) return
        _status.value = BrowserStatus.Installing
        scope.launch {
            try {
                KCEF.init(
                    builder = {
                        installDir(installDir)
                        progress {
                            onDownloading {
                                _status.value = BrowserStatus.Downloading(max(it, UNKNOWN))
                            }
                            onExtracting { _status.value = BrowserStatus.Installing }
                            onInitialized { _status.value = BrowserStatus.Ready }
                        }
                        settings {
                            cachePath = installDir.resolveSibling(CACHE_DIR).absolutePath
                        }
                    },
                    onError = { _status.value = BrowserStatus.Failed(it?.message) },
                    onRestartRequired = { _status.value = BrowserStatus.RestartRequired }
                )
            } catch (e: Exception) {
                _status.value = BrowserStatus.Failed(e.message)
            }
        }
    }

    @Composable
    override fun Page(url: String, reload: Int, modifier: Modifier) {
        val created = remember { url }
        val browser = remember { client.createBrowser(created, CefRendering.DEFAULT, false) }
        DisposableEffect(browser) { onDispose { browser.dispose() } }
        LaunchedEffect(url) { if (url != created) browser.loadURL(url) }
        LaunchedEffect(reload) { if (reload > 0) browser.reload() }
        SwingPanel(factory = { browser.uiComponent }, modifier = modifier)
    }

    @Composable
    override fun Document(payload: String, onRequest: (String) -> Unit, modifier: Modifier) {
        val doc = remember { documentCount.incrementAndGet() }
        val view = remember { DocumentBridge.View(onRequest) }
        view.onRequest = onRequest
        val browser = remember {
            documents.attach(doc, view)
            client.createBrowser(DocumentBridge.hostUrl(host, doc), CefRendering.DEFAULT, false)
                .also { view.browser = it }
        }
        DisposableEffect(browser) {
            onDispose {
                documents.detach(doc)
                browser.dispose()
            }
        }
        LaunchedEffect(payload) { view.show(payload) }
        SwingPanel(factory = { browser.uiComponent }, modifier = modifier)
    }

    /** 앱을 닫을 때 부른다. 엔진을 띄운 적이 없으면 아무것도 하지 않는다. */
    fun dispose() {
        if (started.get()) KCEF.disposeBlocking()
    }

    private companion object {
        const val UNKNOWN = -1f
        const val CACHE_DIR = "kcef-cache"
    }
}
