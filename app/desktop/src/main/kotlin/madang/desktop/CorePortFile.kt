package madang.desktop

import java.io.File
import madang.shared.core.PortFileReader

/** `<앱 홈>/core.port`를 읽는다. 앱이 앱 홈에서 읽는 유일한 파일이다. */
class CorePortFile(private val home: File) : PortFileReader {
    override fun readPort(): Int? = runCatching {
        home.resolve("core.port").readText().trim().toInt().takeIf { it in 1..65535 }
    }.getOrNull()
}
