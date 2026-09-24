package madang.desktop

import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import madang.shared.onboarding.ToolProbe
import madang.shared.onboarding.ToolStatus

/** `which`(Windows는 `where`)와 `--version`으로 도구를 확인한다. 인증 파일은 보지 않는다. */
class CommandToolProbe : ToolProbe {

    private val locator = if (System.getProperty("os.name").lowercase().contains("win")) {
        "where"
    } else {
        "which"
    }

    override suspend fun probe(tool: String): ToolStatus = withContext(Dispatchers.IO) {
        val path = run(locator, tool)?.lineSequence()?.firstOrNull { it.isNotBlank() }?.trim()
            ?: return@withContext ToolStatus(path = null, version = null)
        val version = run(path, "--version")?.lineSequence()?.firstOrNull()?.trim()
        ToolStatus(path = path, version = version)
    }

    /** 명령을 실행해 출력을 돌려준다. 실패하거나 시간이 넘으면 null. */
    private fun run(vararg command: String): String? = runCatching {
        val process = ProcessBuilder(*command).redirectErrorStream(true).start()
        if (!process.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            process.destroy()
            return null
        }
        process.inputStream.bufferedReader().readText().takeIf { process.exitValue() == 0 }
    }.getOrNull()

    private companion object {
        const val TIMEOUT_SECONDS = 10L
    }
}
