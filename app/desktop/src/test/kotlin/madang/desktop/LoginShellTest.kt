package madang.desktop

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.runBlocking

/** 사용자 셸 대신 임시 폴더의 가짜 셸을 쓴다. 가짜 셸은 `-lc` 인자만 받는다. */
class LoginShellTest {

    private val dir: File = Files.createTempDirectory("madang-shell-test").toFile()
    private val isWindows = System.getProperty("os.name").lowercase().contains("win")
    private val toolBin: File = dir.resolve("tools").apply { mkdirs() }
    private val loginPath = "${toolBin.path}:/usr/bin:/bin"

    @AfterTest
    fun cleanUp() {
        dir.deleteRecursively()
    }

    /** 셸 설정이 한 줄을 찍은 뒤, 로그인 PATH로 받은 스크립트를 실행하는 셸. */
    private fun loginShell(): LoginShell = LoginShell(
        fakeShell(
            "[ \"\$1\" = '-lc' ] || exit 8\n" +
                "echo 'welcome from profile'\n" +
                "PATH='$loginPath' exec /bin/sh -c \"\$2\""
        ).path
    )

    /** 받은 스크립트와 상관없이 [body]대로 답하는 셸. */
    private fun fakeShell(body: String, name: String = "fake-shell"): File =
        dir.resolve(name).apply {
            writeText("#!/bin/sh\n$body\n")
            setExecutable(true)
        }

    private fun tool(name: String): File = toolBin.resolve(name).apply {
        writeText("#!/bin/sh\nexit 0\n")
        setExecutable(true)
    }

    @Test
    fun toolIsFoundOnTheLoginShellPath() {
        if (isWindows) return
        val claude = tool("claude")

        assertEquals(claude.path, loginShell().commandPath("claude"))
    }

    @Test
    fun toolMissingFromTheLoginShellIsNotFound() {
        if (isWindows) return

        assertNull(loginShell().commandPath("madang-no-such-tool"))
    }

    @Test
    fun aliasOrNonExecutableAnswerIsNotFound() {
        if (isWindows) return
        val alias = LoginShell(fakeShell("echo \"alias claude='npx claude'\"").path)
        assertNull(alias.commandPath("claude"))

        val plain = dir.resolve("plain").apply { writeText("not a program") }
        val notExecutable = LoginShell(fakeShell("echo '${plain.path}'", "plain-shell").path)
        assertNull(notExecutable.commandPath("claude"))
    }

    @Test
    fun failingOrSlowShellGivesNothing() {
        if (isWindows) return
        assertNull(LoginShell(fakeShell("echo /bin/sh\nexit 1").path).run("command -v sh"))
        assertNull(
            LoginShell(fakeShell("sleep 5", "slow-shell").path, timeoutSeconds = 1).run("true")
        )
        assertNull(LoginShell(dir.resolve("no-such-shell").path).run("true"))
        assertNull(LoginShell(shell = null).path())
    }

    @Test
    fun pathIsTheLoginShellPath() {
        if (isWindows) return

        assertEquals(loginPath, loginShell().path())
    }

    @Test
    fun toolNameCannotCarryShellSyntax() {
        assertFailsWith<IllegalArgumentException> { loginShell().commandPath("claude; true") }
    }

    @Test
    fun locatorAcceptsOnlyAbsoluteExecutableFiles() = runBlocking {
        if (isWindows) return@runBlocking
        val claude = tool("claude")
        val locator = ShellToolLocator(loginShell())

        assertEquals(claude.path, locator.locate("claude"))
        assertTrue(locator.isExecutable(claude.path))
        assertFalse(locator.isExecutable("claude"))
        assertFalse(locator.isExecutable(toolBin.path))
        assertFalse(locator.isExecutable(dir.resolve("missing").path))
    }
}
