package madang.desktop.fake

import java.io.File
import java.time.OffsetDateTime
import java.time.temporal.ChronoUnit
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.jsonObject
import madang.api.model.GitBranches
import madang.api.model.GitFile
import madang.api.model.GitLogEntry
import madang.api.model.GitStatus
import madang.api.model.GitWorktree
import madang.api.model.Project
import madang.shared.core.CoreClient
import madang.shared.main.DiffFile
import madang.shared.main.parseDiff

/**
 * 픽스처의 git 응답. `git/<프로젝트 id>.diff`가 있는 프로젝트만 git 저장소로 보고, 그 파일을 작업
 * 트리의 diff로 돌려준다. 작업 폴더는 프로젝트 폴더다. 선택 `git/<프로젝트 id>.json`(브랜치·워크트리·
 * 로그)을 git 탭에 쓴다.
 *
 * 스테이지·커밋·git 시작은 메모리에만 반영한다: 스테이지하면 상태 코드의 인덱스 글자가 서고,
 * 커밋하면 스테이지한 파일이 상태에서 빠지고 로그 맨 앞에 붙는다. git 시작한 프로젝트는 변경 없는
 * 저장소가 된다.
 */
class FixtureGit(private val dir: File) {

    private val staged = mutableMapOf<String, Set<String>>()
    private val committed = mutableMapOf<String, Set<String>>()
    private val commits = mutableMapOf<String, List<GitLogEntry>>()
    private val initialized = mutableSetOf<String>()

    /** 프로젝트의 diff 텍스트. git 저장소가 아니면 null. */
    fun diff(project: String): String? =
        File(dir, "git/$project.diff").takeIf { it.isFile }?.readText()

    fun isRepository(project: String): Boolean = diff(project) != null || project in initialized

    fun status(project: Project): GitStatus {
        if (!isRepository(project.id)) return GitStatus(false, project.path, emptyList())
        val done = committed[project.id].orEmpty()
        val index = staged[project.id].orEmpty()
        val files = parseDiff(diff(project.id).orEmpty())
            .filter { it.path !in done }
            .map { file ->
                val code = statusCode(file.change)
                GitFile(file.path, if (file.path in index) indexCode(code) else code)
            }
        return GitStatus(true, project.path, files, branch = "main")
    }

    fun branches(project: String): GitBranches = GitBranches(
        branches = extra(project, "branches", String.serializer()) ?: listOf("main"),
        current = "main"
    )

    fun worktrees(project: Project): List<GitWorktree> =
        extra(project.id, "worktrees", GitWorktree.serializer())
            ?: listOf(GitWorktree(path = project.path, head = "", main = true, branch = "main"))

    fun log(project: String, limit: Int): List<GitLogEntry> = (
        commits[project].orEmpty() +
            extra(project, "log", GitLogEntry.serializer()).orEmpty()
        ).take(limit)

    /** [paths](없으면 모든 변경)를 스테이지한다. */
    fun stage(project: Project, paths: List<String>?) {
        val changed = status(project).files.map { it.path }
        staged[project.id] =
            staged[project.id].orEmpty() + (paths ?: changed).filter { it in changed }
    }

    /** 스테이지한 파일을 커밋한다. 스테이지한 것이 없으면 null. */
    fun commit(project: Project, message: String): String? {
        val index = staged[project.id].orEmpty().takeIf { it.isNotEmpty() } ?: return null
        val hash = "%040x".format(message.hashCode().toLong() and 0xffffffffL)
        committed[project.id] = committed[project.id].orEmpty() + index
        staged[project.id] = emptySet()
        val now = OffsetDateTime.now().truncatedTo(ChronoUnit.SECONDS).toString()
        commits[project.id] =
            listOf(GitLogEntry(hash, "me", now, message)) + commits[project.id].orEmpty()
        return hash
    }

    /** 저장소가 아니던 프로젝트를 변경 없는 저장소로 만든다. 이미 저장소면 거짓. */
    fun init(project: String): Boolean = !isRepository(project) && initialized.add(project)

    /** `git/<프로젝트 id>.json`의 [key] 목록(branches·worktrees·log). 없으면 null. */
    private fun <T> extra(project: String, key: String, item: KSerializer<T>): List<T>? {
        val file = File(dir, "git/$project.json").takeIf { it.isFile } ?: return null
        val json = CoreClient.CoreJson
        val element = json.parseToJsonElement(file.readText()).jsonObject[key] ?: return null
        return json.decodeFromJsonElement(ListSerializer(item), element)
    }

    private fun statusCode(change: DiffFile.Change): String = when (change) {
        DiffFile.Change.ADDED -> "A "
        DiffFile.Change.DELETED -> " D"
        DiffFile.Change.RENAMED -> "R "
        DiffFile.Change.MODIFIED -> " M"
    }

    /** 작업 트리 글자를 인덱스 글자로 옮긴다. */
    private fun indexCode(code: String): String = if (code[0] != ' ') code else "${code[1]} "
}
