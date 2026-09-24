package madang.desktop

import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * 사용자의 로그인 셸(`$SHELL -lc <script>`)로 짧은 명령을 실행한다.
 *
 * Finder 등으로 연 앱은 셸 PATH를 받지 않는다. 사용자가 터미널에서 쓰는 PATH와 도구 경로는
 * 로그인 셸에 물어서만 얻는다. 셸 설정 파일은 읽거나 고치지 않고 셸이 스스로 읽게 둔다.
 *
 * @param shell 셸 실행 파일. null이면(Windows 등 `$SHELL`이 없는 곳) 아무것도 실행하지 않는다.
 */
class LoginShell(
    private val shell: String? = defaultShell(),
    private val timeoutSeconds: Long = TIMEOUT_SECONDS
) {

    /** [script]의 표준 출력. 셸이 없거나, 실패하거나, 제한 시간을 넘기면 null. */
    fun run(script: String): String? {
        val shell = shell ?: return null
        val output = File.createTempFile("madang-shell", ".out")
        return try {
            val process = ProcessBuilder(shell, "-lc", script)
                .redirectInput(ProcessBuilder.Redirect.from(NULL_DEVICE))
                .redirectOutput(output)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start()
            if (!process.waitFor(timeoutSeconds, TimeUnit.SECONDS)) {
                process.destroyForcibly()
                return null
            }
            output.readText().takeIf { process.exitValue() == 0 }
        } catch (e: IOException) {
            null
        } finally {
            output.delete()
        }
    }

    /**
     * 로그인 셸의 PATH. 셸 설정이 출력한 다른 줄이 앞에 섞일 수 있어 마지막 줄만 쓴다.
     * 얻지 못하면 null.
     */
    fun path(): String? = run(PRINT_PATH)?.lines()?.lastOrNull { it.isNotBlank() }

    /**
     * 로그인 셸이 `command -v`로 찾은 [tool]의 절대 경로. 별칭·함수처럼 파일이 아닌 결과와
     * 실행할 수 없는 파일은 찾지 못한 것으로 본다.
     */
    fun commandPath(tool: String): String? {
        require(TOOL_NAME.matches(tool)) { "invalid tool name: $tool" }
        return run("command -v $tool")
            ?.lines()
            ?.lastOrNull { it.isNotBlank() }
            ?.trim()
            ?.takeIf { isExecutableFile(it) }
    }

    companion object {
        private const val TIMEOUT_SECONDS = 10L
        private const val PRINT_PATH = "printf '%s\\n' \"\$PATH\""
        private val TOOL_NAME = Regex("[A-Za-z0-9._-]+")
        private val NULL_DEVICE = File("/dev/null")

        private fun defaultShell(): String? {
            if (System.getProperty("os.name").lowercase().contains("win")) return null
            return System.getenv("SHELL")?.takeIf { it.isNotBlank() } ?: "/bin/sh"
        }

        /** 실행할 수 있는 파일의 절대 경로인가. */
        fun isExecutableFile(path: String): Boolean {
            val file = File(path)
            return file.isAbsolute && file.isFile && file.canExecute()
        }
    }
}
