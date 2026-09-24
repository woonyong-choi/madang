package madang.desktop.fake

import madang.api.model.Issue
import org.yaml.snakeyaml.Yaml
import org.yaml.snakeyaml.error.MarkedYAMLException
import org.yaml.snakeyaml.error.YAMLException

/**
 * 가짜 core의 설정 파일: 앱 홈 `config.yaml` 하나와 프로젝트마다 `.madang/config.yaml`.
 *
 * 저장은 core처럼 검사를 통과해야 한다. 올바른 YAML 매핑이어야 하고(`invalid-yaml`), 프로젝트
 * 설정은 알려진 최상위 키만 받는다(`invalid-value`, 그 키의 줄). 값의 형식까지는 보지 않는다.
 */
class FakeConfig {

    private var global = SAMPLE_GLOBAL
    private val projects = mutableMapOf<String, String>()

    fun global(): String = global

    /** 프로젝트 설정 원문. 파일이 없으면 core처럼 빈 문자열이다. */
    fun project(id: String): String = projects[id].orEmpty()

    /** 앱 홈 설정을 [text]로 바꾼다. 검사에 걸리면 바꾸지 않고 문제를 돌려준다. */
    fun saveGlobal(text: String): List<Issue> =
        check(text, allowed = null).also { if (it.isEmpty()) global = text }

    /** 프로젝트 [id]의 설정을 [text]로 바꾼다. 검사에 걸리면 바꾸지 않고 문제를 돌려준다. */
    fun saveProject(id: String, text: String): List<Issue> =
        check(text, PROJECT_KEYS).also { if (it.isEmpty()) projects[id] = text }

    private fun check(text: String, allowed: Set<String>?): List<Issue> {
        val data = try {
            Yaml().load<Any?>(text)
        } catch (e: MarkedYAMLException) {
            val line = e.problemMark?.line?.plus(1)
            return listOf(issue("invalid-yaml", "invalid YAML: ${e.problem}", line))
        } catch (e: YAMLException) {
            return listOf(issue("invalid-yaml", "invalid YAML: ${e.message}", null))
        }
        if (data == null) return emptyList()
        if (data !is Map<*, *>) return listOf(issue("invalid-value", "must be a mapping", 1))
        if (allowed == null) return emptyList()
        return data.keys.map { "$it" }.filter { it !in allowed }.map { key ->
            val line = text.lines().indexOfFirst { it.startsWith("$key:") } + 1
            issue(
                "invalid-value",
                "$key: extra inputs are not permitted",
                line.takeIf { it > 0 }
            )
        }
    }

    private fun issue(code: String, message: String, line: Int?) =
        Issue(code = code, message = message, line = line, path = CONFIG_FILE)

    private companion object {
        const val CONFIG_FILE = "config.yaml"
        val PROJECT_KEYS = setOf("track", "runs", "policy", "publish", "viewers")

        val SAMPLE_GLOBAL = """
            # Madang 전역 설정. 앱(core)이 읽는다. 에이전트는 이 파일을 받지 않는다.
            # 기억(나에 대한 메모)은 profile.md에 둔다.
            core:
              port: 7470
              bind: 127.0.0.1
            limits:
              ledger_tokens: 2000
              block_input_tokens: 4000
            ui:
              language: ko
        """.trimIndent() + "\n"
    }
}
