package madang.desktop.fake

import madang.api.model.Issue
import madang.api.model.MemoryFile
import madang.api.model.MemoryLayer
import madang.api.model.PageDetail
import madang.api.model.Project

/**
 * 픽스처의 메모리 3층(앱 홈 root.md, 프로젝트 `.madang/project.md`, 페이지 state.md). 처음
 * 내용은 프로젝트·페이지에서 만든다. 경로는 core처럼 절대 경로다.
 *
 * state.md 저장은 core 검사기처럼 머리부 필수 키·열거형, 필수 절, 토큰 상한을 확인하고 문제를
 * 줄 번호와 함께 돌려준다. 토큰 수는 네 글자를 한 토큰으로 어림한다.
 */
class FixtureMemory {

    private var root = DEFAULT_ROOT
    private val projects = mutableMapOf<String, String>()
    private val states = mutableMapOf<String, String>()

    fun root(): MemoryFile = file(MemoryLayer.ROOT, ROOT_PATH, root)

    fun project(project: Project): MemoryFile = file(
        MemoryLayer.PROJECT,
        "${project.path}/.madang/project.md",
        projects.getOrPut(project.id) { "# ${project.title}\n${project.title} 프로젝트의 메모.\n" }
    )

    fun state(page: PageDetail, project: Project): MemoryFile = file(
        MemoryLayer.STATE,
        "${project.path}/.madang/pages/${page.id}/state.md",
        states.getOrPut(page.id) { initialState(page) }
    )

    /** [layer]를 [content]로 저장한다. 검사에 걸리면 저장하지 않고 문제를 돌려준다. */
    fun save(page: PageDetail, layer: MemoryLayer, content: String): List<Issue> {
        if (layer == MemoryLayer.STATE) {
            val issues = checkState(content)
            if (issues.isNotEmpty()) return issues
        }
        when (layer) {
            MemoryLayer.ROOT -> root = content
            MemoryLayer.PROJECT -> projects[page.project] = content
            MemoryLayer.STATE -> states[page.id] = content
        }
        return emptyList()
    }

    private fun file(layer: MemoryLayer, path: String, content: String) = MemoryFile(
        layer = layer,
        path = path,
        content = content,
        tokens = tokens(content),
        tokenLimit = STATE_TOKEN_LIMIT.takeIf { layer == MemoryLayer.STATE }
    )

    private fun initialState(page: PageDetail) = """
        ---
        status: ${page.status.value}
        kind: ${page.kind ?: "build"}
        tier: 1
        attempts: 0
        ---
        ## 목표
        ${page.title}

        ## 다음 할 일
        1. 결과를 사람이 검토한다.
    """.trimIndent() + "\n"

    companion object {
        const val STATE_TOKEN_LIMIT = 2000

        private val REQUIRED_KEYS = listOf("status", "kind", "tier", "attempts")
        private val STATUSES = setOf("planning", "doing", "blocked", "review", "done")
        private val REQUIRED_SECTIONS = listOf("목표", "다음 할 일")
        private const val ROOT_PATH = "/Users/me/.madang/root.md"
        private const val DEFAULT_ROOT = "# 나에 대해\n한국어로 답한다. 확인 질문 없이 진행한다.\n"

        fun tokens(text: String): Int = (text.length + 3) / 4

        /** state.md 검사. 문제가 없으면 빈 목록. */
        fun checkState(content: String): List<Issue> {
            val lines = content.lines()
            if (lines.firstOrNull() != "---") {
                return listOf(issue("missing-front-matter", "front matter must start with ---", 1))
            }
            val end = lines.drop(1).indexOf("---").takeIf { it >= 0 }?.plus(1)
                ?: return listOf(issue("missing-front-matter", "front matter is not closed", 1))
            val keys = (1 until end).associateBy { lines[it].substringBefore(':').trim() }
            val issues = mutableListOf<Issue>()
            REQUIRED_KEYS.filter { it !in keys }.forEach {
                issues += issue("missing-key", "missing required key '$it'", end + 1)
            }
            keys["status"]?.let { index ->
                val value = lines[index].substringAfter(':').substringBefore('#').trim()
                if (value !in STATUSES) {
                    issues += issue(
                        "invalid-value",
                        "status: expected ${STATUSES.joinToString(" | ")}",
                        index + 1
                    )
                }
            }
            listOf("tier", "attempts").forEach { key ->
                val index = keys[key] ?: return@forEach
                if (lines[index].substringAfter(':').trim().toIntOrNull() == null) {
                    issues += issue("invalid-value", "$key: expected an integer", index + 1)
                }
            }
            REQUIRED_SECTIONS.filter { section -> lines.none { it.trim() == "## $section" } }
                .forEach { issues += issue("missing-section", "missing section '## $it'", null) }
            val count = tokens(content)
            if (count > STATE_TOKEN_LIMIT) {
                issues += issue(
                    "token-limit",
                    "state.md is $count tokens (limit $STATE_TOKEN_LIMIT); summarize the log",
                    null
                )
            }
            return issues
        }

        private fun issue(code: String, message: String, line: Int?) =
            Issue(code = code, message = message, line = line, path = "state.md")
    }
}
