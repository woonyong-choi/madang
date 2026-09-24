package madang.shared.onboarding

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import madang.shared.main.loadYaml

class RunnerBinTest {

    @Test
    fun replacesBinAndKeepsCommentsAndOtherKeys() {
        val updated = withRunnerBin(CONFIG, "claude", "/Users/me/.local/bin/claude")

        assertEquals(
            CONFIG.replace("    bin: claude\n", "    bin: \"/Users/me/.local/bin/claude\"\n"),
            updated
        )
        assertEquals("/Users/me/.local/bin/claude", bin(updated, "claude"))
        assertEquals("codex", bin(updated, "codex"))
    }

    @Test
    fun addsMissingBinUnderExistingRunner() {
        val config = "runners:\n  codex:\n    args: [exec]\n"

        val updated = withRunnerBin(config, "codex", "/opt/codex")

        assertEquals("runners:\n  codex:\n    bin: \"/opt/codex\"\n    args: [exec]\n", updated)
    }

    @Test
    fun addsMissingRunnerBeforeTrailingComments() {
        val config = "runners:\n    claude:\n        bin: claude\n\n# 끝\nui:\n  language: ko\n"

        val updated = withRunnerBin(config, "codex", "/opt/codex")

        assertEquals("/opt/codex", bin(updated, "codex"))
        assertEquals("claude", bin(updated, "claude"))
        assertEquals(
            "runners:\n    claude:\n        bin: claude\n    codex:\n      bin: \"/opt/codex\"\n" +
                "\n# 끝\nui:\n  language: ko\n",
            updated
        )
    }

    @Test
    fun addsRunnersSectionWhenAbsent() {
        val updated = withRunnerBin("ui:\n  language: ko", "claude", "/opt/claude")

        assertEquals(
            "ui:\n  language: ko\nrunners:\n  claude:\n    bin: \"/opt/claude\"\n",
            updated
        )
    }

    @Test
    fun quotesPathsWithSpacesAndQuotes() {
        val path = "/Users/me/My Tools/cl\"aude #1"

        assertEquals(path, bin(withRunnerBin(CONFIG, "claude", path), "claude"))
    }

    @Test
    fun inlineRunnersCannotBeEdited() {
        assertFailsWith<IllegalArgumentException> {
            withRunnerBin("runners: {claude: {bin: claude}}\n", "claude", "/opt/claude")
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun bin(config: String, runner: String): Any? {
        val root = loadYaml(config) as Map<String, Any?>
        val runners = root["runners"] as Map<String, Any?>
        return (runners[runner] as Map<String, Any?>)["bin"]
    }

    private companion object {
        val CONFIG = """
            # 전역 설정
            core:
              port: 7470

            # 도구 경로와 실행 방법
            runners:
              claude:
                bin: claude
                args: ["-p", "--output-format", "stream-json",
                       "--model", "{model}"]
                auth: subscription            # subscription | api
              codex:
                bin: codex
                args: ["exec", "--json"]
        """.trimIndent() + "\n"
    }
}
