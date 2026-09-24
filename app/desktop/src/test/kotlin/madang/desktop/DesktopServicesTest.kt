package madang.desktop

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.coroutines.runBlocking
import madang.shared.core.CoreProcess
import madang.shared.onboarding.ClaudeStatus
import madang.shared.settings.AppSettings
import madang.shared.settings.Language

class DesktopServicesTest {

    private val dir: File = Files.createTempDirectory("madang-desktop-test").toFile()
    private val isWindows = System.getProperty("os.name").lowercase().contains("win")

    @AfterTest
    fun cleanUp() {
        dir.deleteRecursively()
    }

    @Test
    fun portFileIsReadWhenValid() {
        val portFile = CorePortFile(dir)
        assertNull(portFile.readPort())

        dir.resolve("core.port").writeText("7481\n")
        assertEquals(7481, portFile.readPort())

        dir.resolve("core.port").writeText("not a port")
        assertNull(portFile.readPort())
    }

    @Test
    fun settingsRoundTrip() {
        val store = FileSettingsStore(dir.resolve("nested/settings.json"))
        assertEquals(AppSettings(), store.load())

        val settings = AppSettings(coreUrl = "http://127.0.0.1:7481", language = Language.EN)
        store.save(settings)

        assertEquals(settings, FileSettingsStore(dir.resolve("nested/settings.json")).load())
    }

    @Test
    fun configuredBinaryWinsOverDevelopmentCommand() {
        val launcher = ProcessCoreLauncher(AppSettings(coreBinary = "/opt/madang/madang-core")) {
            null
        }

        assertEquals(listOf("/opt/madang/madang-core", "serve"), launcher.command())
    }

    @Test
    fun developmentCommandUsesUv() {
        val previous = System.setProperty("madang.coreProject", "/repo/core")
        try {
            assertEquals(
                listOf("uv", "run", "--project", "/repo/core", "madang", "serve"),
                ProcessCoreLauncher(AppSettings()).command()
            )
        } finally {
            if (previous == null) {
                System.clearProperty("madang.coreProject")
            } else {
                System.setProperty("madang.coreProject", previous)
            }
        }
    }

    @Test
    fun exitedCoreReportsCodeAndOutput() {
        if (isWindows) return
        val script = dir.resolve("fake-core.sh").apply {
            writeText("#!/bin/sh\necho \"unknown command: \$1\"\nexit 2\n")
            setExecutable(true)
        }
        val process = ProcessCoreLauncher(AppSettings(coreBinary = script.path)) { null }.launch()

        assertEquals("exit 2: unknown command: serve", awaitExit(process))
    }

    private fun awaitExit(process: CoreProcess): String {
        var detail = process.exitDetail()
        var polls = 0
        while (detail == null && polls++ < 50) {
            Thread.sleep(100)
            detail = process.exitDetail()
        }
        return assertNotNull(detail)
    }

    /** [dir] 아래 [path]에 실행할 수 있는 sh 스크립트를 만든다. */
    private fun script(path: String, body: String): File = dir.resolve(path).apply {
        parentFile.mkdirs()
        writeText("#!/bin/sh\n$body\n")
        setExecutable(true)
    }

    @Test
    fun homeExpandsTilde() {
        val home = File(System.getProperty("user.home"))
        assertEquals(home.resolve("work/madang"), DesktopPaths.expandHome("~/work/madang"))
        assertEquals(
            home.resolve("elsewhere"),
            DesktopPaths.appHome(AppSettings(homePath = "~/elsewhere"))
        )
    }

    @Test
    fun claudeAuthStatusKeepsOnlyLoginAndMethod() {
        val loggedIn = parseAuthStatus(
            """{"loggedIn": true, "authMethod": "claude.ai", "email": "me@example.com"}"""
        )
        assertEquals(
            ClaudeStatus(installed = true, loggedIn = true, authMethod = "claude.ai"),
            loggedIn
        )

        val loggedOut = parseAuthStatus("""{"loggedIn": false, "authMethod": "none"}""")
        assertEquals(ClaudeStatus(installed = true, loggedIn = false), loggedOut)

        assertEquals(ClaudeStatus(installed = true, loggedIn = false), parseAuthStatus("error"))
    }

    @Test
    fun missingClaudeCommandIsNotInstalled() = runBlocking {
        val status = CommandClaudeProbe().check(dir.resolve("no-such-claude").path)

        assertEquals(ClaudeStatus(installed = false, loggedIn = false), status)
    }

    @Test
    fun claudeIsCheckedAtTheGivenPath() = runBlocking {
        if (isWindows) return@runBlocking
        val claude = script(
            "bin/claude",
            "[ \"\$1 \$2\" = 'auth status' ] || exit 9\n" +
                "echo '{\"loggedIn\": true, \"authMethod\": \"claude.ai\"}'"
        )

        assertEquals(
            ClaudeStatus(installed = true, loggedIn = true, authMethod = "claude.ai"),
            CommandClaudeProbe().check(claude.path)
        )
    }

    @Test
    fun bundledCoreIsTheExecutableInsideTheOnedirFolder() {
        if (isWindows) return
        val resources = dir.resolve("resources")
        val core = script("resources/madang-core/madang", "exit 0")
        resources.resolve("madang-core/_internal").mkdirs()

        val launcher = ProcessCoreLauncher(AppSettings(), resources.path) { null }

        assertEquals(core, launcher.bundledBinary())
        if (System.getProperty("madang.coreProject") == null) {
            assertEquals(listOf(core.path, "serve"), launcher.command())
        }
    }

    @Test
    fun onedirFolderItselfIsNotTheBundledCore() {
        val resources = dir.resolve("resources").apply { resolve("madang-core").mkdirs() }

        assertNull(ProcessCoreLauncher(AppSettings(), resources.path) { null }.bundledBinary())
        assertNull(ProcessCoreLauncher(AppSettings(), null) { null }.bundledBinary())
    }

    @Test
    fun coreGetsTheLoginShellPath() {
        if (isWindows) return
        val core = script("fake-core.sh", "echo \"PATH=\$PATH\"\nexit 3")
        val loginPath = "/Users/me/.local/bin:/usr/bin:/bin"
        val process = ProcessCoreLauncher(AppSettings(coreBinary = core.path)) { loginPath }
            .launch()

        assertEquals("exit 3: PATH=$loginPath", awaitExit(process))
    }

    @Test
    fun missingLoginPathKeepsTheAppEnvironment() {
        val launcher = ProcessCoreLauncher(AppSettings(homePath = "/work/home")) { null }

        assertEquals(mapOf("MADANG_HOME" to "/work/home"), launcher.environment())
    }
}
