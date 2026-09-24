package madang.desktop

import java.io.File
import madang.shared.core.CoreLauncher
import madang.shared.core.CoreProcess
import madang.shared.settings.AppSettings

/**
 * core 프로세스를 띄운다.
 *
 * 명령 순서: 설정의 실행 파일 → 개발 실행(`uv run --project <core> madang serve`,
 * 시스템 속성 `madang.coreProject`) → 동봉 실행 파일(패키지 리소스 폴더의 `madang-core`).
 */
class ProcessCoreLauncher(private val settings: AppSettings) : CoreLauncher {

    override fun launch(): CoreProcess {
        val command = command() ?: error(
            "no core binary: set the core binary path in settings or run from the repository"
        )
        val builder = ProcessBuilder(command).redirectErrorStream(true)
        settings.homePath?.let {
            builder.environment()["MADANG_HOME"] = DesktopPaths.expandHome(it).path
        }
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

    private fun bundledBinary(): File? {
        val dir = System.getProperty("compose.application.resources.dir") ?: return null
        val name = if (System.getProperty("os.name").lowercase().contains("win")) {
            "madang-core.exe"
        } else {
            "madang-core"
        }
        return File(dir, name).takeIf { it.canExecute() }
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
