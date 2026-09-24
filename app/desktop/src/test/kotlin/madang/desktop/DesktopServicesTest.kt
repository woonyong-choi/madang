package madang.desktop

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import madang.shared.settings.AppSettings
import madang.shared.settings.Language

class DesktopServicesTest {

    private val dir: File = Files.createTempDirectory("madang-desktop-test").toFile()

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
        val launcher = ProcessCoreLauncher(AppSettings(coreBinary = "/opt/madang/madang-core"))

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
        if (System.getProperty("os.name").lowercase().contains("win")) return
        val script = dir.resolve("fake-core.sh").apply {
            writeText("#!/bin/sh\necho \"unknown command: \$1\"\nexit 2\n")
            setExecutable(true)
        }
        val process = ProcessCoreLauncher(AppSettings(coreBinary = script.path)).launch()

        var detail = process.exitDetail()
        var polls = 0
        while (detail == null && polls++ < 50) {
            Thread.sleep(100)
            detail = process.exitDetail()
        }

        assertEquals("exit 2: unknown command: serve", assertNotNull(detail))
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
}
