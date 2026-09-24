package madang.desktop

import dev.datlag.kcef.KCEF
import java.awt.Dimension
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import javax.swing.JFrame
import javax.swing.SwingUtilities
import kotlinx.coroutines.flow.distinctUntilChangedBy
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import madang.shared.BrowserStatus
import madang.shared.main.fileUrl
import org.cef.browser.CefBrowser
import org.cef.browser.CefFrame
import org.cef.browser.CefRendering
import org.cef.handler.CefLoadHandler
import org.cef.handler.CefLoadHandlerAdapter

/**
 * 웹 엔진 진단. 앱 화면 없이 문서 탭과 같은 길로 CEF를 띄우고, 브라우저 하나로 로컬 html(문서 탭
 * 호스트)을 읽어 본다. 진행을 `madang: probe …` 줄로 찍는다.
 *
 * 브라우저는 보이는 창에 붙어야 페이지를 읽으므로 작은 창을 잠깐 띄운다. 창을 조작할 필요는 없다.
 */
class WebEngineProbe(private val engine: KcefBrowserEngine, private val runtime: DocumentRuntime) {

    /** 0 읽기 완료, 1 준비 실패·읽기 실패·시간 초과, 2 앱을 다시 시작해야 한다. */
    fun run(): Int {
        log("java.home ${System.getProperty("java.home")}")
        log("bundle ${engine.bundleDir.path}")
        val status = prepare() ?: return fail("engine was not ready in ${PREPARE_SECONDS}s")
        return when (status) {
            BrowserStatus.Ready -> load(fileUrl(runtime.install().absolutePath))
            BrowserStatus.RestartRequired -> RESTART_REQUIRED
            else -> FAILED
        }
    }

    private fun prepare(): BrowserStatus? = runBlocking {
        engine.prepare()
        withTimeoutOrNull(TimeUnit.SECONDS.toMillis(PREPARE_SECONDS)) {
            engine.status.distinctUntilChangedBy { it::class }
                .onEach { log("engine $it") }
                .first { it.isSettled() }
        }
    }

    private fun load(url: String): Int {
        val loaded = CompletableFuture<Int>()
        val client = KCEF.newClientBlocking()
        client.addLoadHandler(object : CefLoadHandlerAdapter() {
            override fun onLoadEnd(browser: CefBrowser, frame: CefFrame, httpStatusCode: Int) {
                if (frame.isMain) loaded.complete(httpStatusCode)
            }

            override fun onLoadError(
                browser: CefBrowser,
                frame: CefFrame,
                errorCode: CefLoadHandler.ErrorCode,
                errorText: String?,
                failedUrl: String?
            ) {
                if (!frame.isMain) return
                loaded.completeExceptionally(IllegalStateException("$errorCode $errorText"))
            }
        })
        val browser = client.createBrowser(url, CefRendering.DEFAULT, false)
        val frame = JFrame("Madang web engine probe")
        SwingUtilities.invokeAndWait {
            frame.contentPane.add(browser.uiComponent)
            frame.size = Dimension(WINDOW_SIZE, WINDOW_SIZE)
            frame.isVisible = true
        }
        log("loading $url")
        val code = try {
            loaded.get(LOAD_SECONDS, TimeUnit.SECONDS)
        } catch (e: TimeoutException) {
            return fail("page did not load in ${LOAD_SECONDS}s")
        } catch (e: Exception) {
            return fail("page failed to load: ${e.cause?.message ?: e.message}")
        } finally {
            SwingUtilities.invokeAndWait { frame.dispose() }
            browser.close(true)
            client.dispose()
        }
        log("loaded $url status $code")
        return OK
    }

    private fun BrowserStatus.isSettled() = this == BrowserStatus.Ready ||
        this == BrowserStatus.RestartRequired || this is BrowserStatus.Failed

    private fun fail(reason: String): Int {
        log("failed: $reason")
        return FAILED
    }

    private fun log(message: String) = println("madang: probe $message")

    private companion object {
        const val OK = 0
        const val FAILED = 1
        const val RESTART_REQUIRED = 2
        const val PREPARE_SECONDS = 600L
        const val LOAD_SECONDS = 60L
        const val WINDOW_SIZE = 400
    }
}
