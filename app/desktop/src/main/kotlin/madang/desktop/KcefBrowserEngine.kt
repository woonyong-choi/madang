package madang.desktop

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.awt.SwingPanel
import dev.datlag.kcef.KCEF
import dev.datlag.kcef.KCEFClient
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
 * 브라우저 탭이나 문서 탭을 처음 열 때 [prepare]가 불린다. [bundle]이 고정 릴리스에서 받은 것이
 * 아니면 지우고 그 릴리스를 내려받아 푼다(첫 실행). CEF를 띄우기 직전에 번들을 다시 검사해 맞지
 * 않으면 띄우지 않고 [BrowserStatus.Failed]로 알린다. 진행은 [status]로 알린다. 캐시는 번들 폴더
 * 옆 `kcef-cache`에 둔다. 문서 탭은 [runtime]의 렌더러 호스트를 연다.
 */
class KcefBrowserEngine(private val bundle: WebEngineBundle, private val runtime: DocumentRuntime) :
    BrowserEngine {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val started = AtomicBoolean(false)
    private val _status = MutableStateFlow<BrowserStatus>(BrowserStatus.Idle)
    override val status: StateFlow<BrowserStatus> = _status.asStateFlow()

    /** 엔진 번들 폴더. */
    val bundleDir get() = bundle.dir

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
        scope.launch { start() }
    }

    /** 번들을 지우고 다시 받는다. 준비에 실패했을 때만 한다. */
    override fun reinstall() {
        if (_status.value !is BrowserStatus.Failed) return
        _status.value = BrowserStatus.Installing
        scope.launch {
            bundle.remove()
            start()
        }
    }

    private suspend fun start() {
        val installed = when (val check = bundle.check()) {
            BundleCheck.Ready -> true

            is BundleCheck.Broken -> {
                _status.value = BrowserStatus.Failed(check.reason)
                return
            }

            // 표식이 없거나 다른 릴리스의 번들, 받다 만 번들은 지우고 고정 릴리스를 다시 받는다.
            BundleCheck.Absent, is BundleCheck.Stale -> {
                bundle.remove()
                false
            }
        }
        try {
            KCEF.init(
                builder = {
                    installDir(bundle.dir)
                    val cefArgs = bundle.cefArgs().toTypedArray()
                    args(*cefArgs)
                    appHandler(KCEF.AppHandler(cefArgs))
                    download { github { release(WebEngineBundle.RELEASE) } }
                    progress {
                        onDownloading {
                            _status.value = BrowserStatus.Downloading(max(it, UNKNOWN))
                        }
                        onExtracting { _status.value = BrowserStatus.Installing }
                        onInitializing { verify(installed) }
                        onInitialized { _status.value = BrowserStatus.Ready }
                    }
                    settings {
                        cachePath = bundle.dir.resolveSibling(CACHE_DIR).absolutePath
                    }
                },
                onError = { _status.value = BrowserStatus.Failed(it?.message) },
                onRestartRequired = {
                    if (!installed) bundle.markInstalled()
                    _status.value = BrowserStatus.RestartRequired
                }
            )
        } catch (e: Exception) {
            _status.value = BrowserStatus.Failed(e.message)
        }
    }

    /**
     * CEF를 띄우기 직전에 불린다. 이번에 받은 번들이면 표식을 남기고, 번들이 맞지 않으면 예외로
     * 초기화를 멈춘다. KCEF는 이 예외를 onError로 넘긴다.
     */
    private fun verify(installed: Boolean) {
        if (!installed) bundle.markInstalled()
        val result = bundle.check()
        check(result == BundleCheck.Ready) { WebEngineBundle.describe(result) }
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
