package madang.desktop

import java.util.concurrent.ConcurrentHashMap
import javax.swing.SwingUtilities
import madang.shared.main.DOCUMENT_SCHEME
import org.cef.browser.CefBrowser
import org.cef.browser.CefFrame
import org.cef.handler.CefLoadHandlerAdapter
import org.cef.handler.CefRequestHandlerAdapter
import org.cef.network.CefRequest

/**
 * 문서 탭 WebView와 앱 사이의 다리. KCEF 처리기는 클라이언트마다 하나라 호스트 주소의 문서 번호
 * (`app.html?doc=N`)로 문서 탭을 나눈다.
 *
 * - 호스트가 다 뜨면([loads]) 마지막 문서를 `madangApp.render()`로 그린다.
 * - 호스트가 `madang-app://…`로 탐색하면([requests]) 막고 그 주소를 문서 탭에 넘긴다. 문서 탭은 그
 *   밖의 곳으로도 가지 않는다. 브라우저 탭의 탐색은 건드리지 않는다.
 */
class DocumentBridge {

    /** 문서 탭 하나. [show]로 받은 문서를 호스트가 준비되는 대로 그린다. */
    class View(@Volatile var onRequest: (String) -> Unit) {
        @Volatile
        var browser: CefBrowser? = null

        @Volatile
        private var loaded = false

        @Volatile
        private var payload: String? = null

        fun show(payload: String) {
            this.payload = payload
            render()
        }

        internal fun onLoaded() {
            loaded = true
            render()
        }

        private fun render() {
            val browser = browser ?: return
            val json = payload ?: return
            if (loaded) browser.executeJavaScript("window.madangApp.render($json);", browser.url, 0)
        }
    }

    private val views = ConcurrentHashMap<Int, View>()

    fun attach(doc: Int, view: View) {
        views[doc] = view
    }

    fun detach(doc: Int) {
        views.remove(doc)
    }

    private fun viewOf(url: String?): View? = url?.let(::documentNumber)?.let(views::get)

    val requests = object : CefRequestHandlerAdapter() {
        override fun onBeforeBrowse(
            browser: CefBrowser,
            frame: CefFrame,
            request: CefRequest,
            userGesture: Boolean,
            isRedirect: Boolean
        ): Boolean {
            val target = request.url
            if (target.startsWith(DOCUMENT_SCHEME)) {
                viewOf(browser.url)?.let { view ->
                    SwingUtilities.invokeLater { view.onRequest(target) }
                }
                return true
            }
            if (!frame.isMain || viewOf(target) != null) return false
            return viewOf(browser.url) != null
        }
    }

    val loads = object : CefLoadHandlerAdapter() {
        override fun onLoadEnd(browser: CefBrowser, frame: CefFrame, httpStatusCode: Int) {
            if (frame.isMain) viewOf(browser.url)?.onLoaded()
        }
    }

    companion object {
        private val DOCUMENT_NUMBER = Regex("app\\.html\\?doc=(\\d+)$")

        /** 호스트 주소. [host]는 `app.html`의 `file:` URL이다. */
        fun hostUrl(host: String, doc: Int): String = "$host?doc=$doc"

        /** 호스트 주소의 문서 번호. 호스트 주소가 아니면 null. */
        fun documentNumber(url: String): Int? =
            DOCUMENT_NUMBER.find(url)?.groupValues?.get(1)?.toIntOrNull()
    }
}
