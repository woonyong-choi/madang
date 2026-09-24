package madang.desktop

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import madang.shared.onboarding.ToolLocator

/** 로그인 셸의 `command -v`로 도구를 찾는다. 사용자가 고른 경로는 파일 자체를 확인한다. */
class ShellToolLocator(private val shell: LoginShell = LoginShell()) : ToolLocator {

    override suspend fun locate(tool: String): String? =
        withContext(Dispatchers.IO) { shell.commandPath(tool) }

    override suspend fun isExecutable(path: String): Boolean =
        withContext(Dispatchers.IO) { LoginShell.isExecutableFile(path) }
}
