package madang.desktop

import java.io.File
import madang.shared.settings.AppSettings

/** 데스크톱 경로 규칙. 앱이 쓰는 곳은 [appConfigDir] 하나뿐이다. */
object DesktopPaths {

    private val userHome: File get() = File(System.getProperty("user.home"))

    /** 앱 설정 폴더. `MADANG_APP_CONFIG_DIR`로 바꿀 수 있다. */
    fun appConfigDir(): File {
        System.getenv("MADANG_APP_CONFIG_DIR")?.let { return File(it) }
        val os = System.getProperty("os.name").lowercase()
        return when {
            os.contains("mac") -> userHome.resolve("Library/Application Support/Madang")

            os.contains("win") ->
                File(System.getenv("APPDATA") ?: userHome.path).resolve("Madang")

            else ->
                File(System.getenv("XDG_CONFIG_HOME") ?: userHome.resolve(".config").path)
                    .resolve("madang")
        }
    }

    /** 앱 홈 경로. 설정 → `MADANG_HOME` → `~/.madang`. 읽기 전용으로만 쓴다. */
    fun appHome(settings: AppSettings): File {
        val configured = settings.homePath ?: System.getenv("MADANG_HOME")
        return configured?.let(::expandHome) ?: userHome.resolve(".madang")
    }

    fun expandHome(path: String): File = when {
        path == "~" -> userHome
        path.startsWith("~/") -> userHome.resolve(path.removePrefix("~/"))
        else -> File(path)
    }
}
