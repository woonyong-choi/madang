package madang.desktop

import java.awt.Desktop
import java.io.File
import java.net.URI
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import madang.shared.LocalFiles

/**
 * 데스크톱의 작업 폴더 파일 읽기와 외부 앱 열기. 파일을 쓰지 않는다.
 *
 * 외부 열기는 URL이면 기본 브라우저, 파일이면 기본 편집기(없으면 기본 앱)다.
 */
class DesktopLocalFiles : LocalFiles {

    override suspend fun read(path: String): String = withContext(Dispatchers.IO) {
        val file = File(path)
        require(file.length() <= MAX_BYTES) { "file is larger than ${MAX_BYTES / MEGABYTE} MB" }
        file.readText()
    }

    override fun openExternally(target: String) {
        if (!Desktop.isDesktopSupported()) return
        val desktop = Desktop.getDesktop()
        // 운영체제가 앱을 띄우는 동안 화면이 멈추지 않도록 따로 부른다.
        Thread {
            runCatching {
                if (URL_SCHEME.containsMatchIn(target)) {
                    desktop.browse(URI(target))
                } else {
                    edit(desktop, File(target))
                }
            }.onFailure { System.err.println("madang: cannot open $target: ${it.message}") }
        }.start()
    }

    private fun edit(desktop: Desktop, file: File) {
        if (desktop.isSupported(Desktop.Action.EDIT)) {
            runCatching { desktop.edit(file) }.onSuccess { return }
        }
        desktop.open(file)
    }

    private companion object {
        const val MEGABYTE = 1_048_576L
        const val MAX_BYTES = 4 * MEGABYTE
        val URL_SCHEME = Regex("^[a-zA-Z][a-zA-Z0-9+.-]*://")
    }
}
