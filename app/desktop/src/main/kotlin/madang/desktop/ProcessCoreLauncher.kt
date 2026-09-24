package madang.desktop

import java.io.File
import madang.shared.core.CoreLauncher
import madang.shared.core.CoreProcess
import madang.shared.settings.AppSettings

/**
 * core 프로세스를 띄운다.
 *
 * 명령 순서: 설정의 실행 파일 → 개발 실행(`uv run --project <core> madang serve`,
 * 시스템 속성 `madang.coreProject`) → 동봉 실행 파일(패키지 리소스 폴더의
 * `madang-core/madang`, PyInstaller onedir).
 *
 * Finder 등으로 연 앱은 셸 PATH를 받지 않으므로, 사용자의 로그인 셸 PATH를 core 환경으로
 * 넘긴다. 에이전트가 부르는 `madang`과 도구를 core 아래에서도 찾게 하기 위해서다.
 *
 * @param resourcesDir 패키지 리소스 폴더. 개발 실행에서는 없다.
 * @param loginPath 로그인 셸의 PATH를 얻는다. 얻지 못하면 앱의 PATH를 그대로 물려준다.
 */
class ProcessCoreLauncher(
    private val settings: AppSettings,
    private val resourcesDir: String? = System.getProperty("compose.application.resources.dir"),
    private val loginPath: () -> String? = { LoginShell().path() }
) : CoreLauncher {

    override fun launch(): CoreProcess {
        val command = command() ?: error(
            "no core binary: set the core binary path in settings or run from the repository"
        )
        val builder = ProcessBuilder(command).redirectErrorStream(true)
        environment().forEach { (key, value) -> builder.environment()[key] = value }
        println("madang: starting core: ${command.joinToString(" ")}")
        return RunningCore(builder.start())
    }

    fun command(): List<String>? {
        settings.coreBinary?.let { return listOf(it, "serve") }
        System.getProperty("madang.coreProject")?.let {
            return listOf("uv", "run", "--project", it, "madang", "serve")
        }
        return bundledBinary()?.let { listOf(it.path, "serve") }
    }

    /** core 환경에 덮어쓸 값. 앱 홈 설정과 로그인 셸 PATH. */
    fun environment(): Map<String, String> = buildMap {
        settings.homePath?.let { put("MADANG_HOME", DesktopPaths.expandHome(it).path) }
        loginPath()?.let { put("PATH", it) }
    }

    /** 동봉 core. onedir 폴더(`madang-core/`) 안의 실행 파일을 띄운다. */
    fun bundledBinary(): File? {
        val dir = resourcesDir ?: return null
        val name = if (System.getProperty("os.name").lowercase().contains("win")) {
            "madang.exe"
        } else {
            "madang"
        }
        return File(dir, "$BUNDLE_DIR/$name").takeIf { it.isFile && it.canExecute() }
    }

    private companion object {
        const val BUNDLE_DIR = "madang-core"
    }
}

/** 띄운 core. 출력은 앱 표준 출력으로 넘기고 마지막 몇 줄은 실패 사유로 남긴다. */
private class RunningCore(private val process: Process) : CoreProcess {

    private val tail = ArrayDeque<String>()
    private val reader = Thread({ pump() }, "madang-core-output").apply { isDaemon = true }

    init {
        reader.start()
        Runtime.getRuntime().addShutdownHook(Thread { process.destroy() })
    }

    override fun exitDetail(): String? {
        if (process.isAlive) return null
        reader.join(OUTPUT_DRAIN_MILLIS)
        val output = synchronized(tail) { tail.joinToString("\n") }
        return "exit ${process.exitValue()}" + if (output.isEmpty()) "" else ": $output"
    }

    override fun stop() {
        process.destroy()
    }

    private fun pump() {
        process.inputStream.bufferedReader().forEachLine { line ->
            println("core: $line")
            synchronized(tail) {
                tail.addLast(line)
                if (tail.size > TAIL_LINES) tail.removeFirst()
            }
        }
    }

    private companion object {
        const val TAIL_LINES = 8
        const val OUTPUT_DRAIN_MILLIS = 500L
    }
}
