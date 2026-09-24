package madang.desktop.fake

import java.io.File
import madang.api.model.GitFile
import madang.api.model.GitStatus
import madang.api.model.Project
import madang.shared.main.DiffFile
import madang.shared.main.parseDiff

/**
 * 픽스처의 git 응답. `git/<프로젝트 id>.diff`가 있는 프로젝트만 git 저장소로 보고, 그 파일을 작업
 * 트리의 diff로 돌려준다. 작업 폴더는 프로젝트 폴더다.
 */
class FixtureGit(private val dir: File) {

    /** 프로젝트의 diff 텍스트. git 저장소가 아니면 null. */
    fun diff(project: String): String? =
        File(dir, "git/$project.diff").takeIf { it.isFile }?.readText()

    fun status(project: Project): GitStatus {
        val diff = diff(project.id) ?: return GitStatus(false, project.path, emptyList())
        val files = parseDiff(diff).map { GitFile(it.path, statusCode(it.change)) }
        return GitStatus(true, project.path, files, branch = "main")
    }

    private fun statusCode(change: DiffFile.Change): String = when (change) {
        DiffFile.Change.ADDED -> "A "
        DiffFile.Change.DELETED -> " D"
        DiffFile.Change.RENAMED -> "R "
        DiffFile.Change.MODIFIED -> " M"
    }
}
