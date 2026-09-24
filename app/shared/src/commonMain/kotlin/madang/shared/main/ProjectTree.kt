package madang.shared.main

import madang.api.model.PageCard
import madang.api.model.PageStatus
import madang.api.model.Project

/** 1열 프로젝트 트리의 한 줄. */
data class ProjectRow(
    val project: Project,
    val depth: Int,
    val hasChildren: Boolean,
    val expanded: Boolean
)

/**
 * 프로젝트 목록을 트리 순서로 펼친다.
 *
 * 같은 부모 안에서 제목순이다. 접힌 프로젝트의 하위는 빠진다.
 * [focus]가 있으면 그 프로젝트와 하위만 보인다.
 */
fun projectRows(
    projects: List<Project>,
    expanded: Set<String>,
    focus: String? = null
): List<ProjectRow> {
    val children = childrenByParent(projects)
    val tops = if (focus != null) projects.filter { it.id == focus } else children[null].orEmpty()
    val rows = mutableListOf<ProjectRow>()
    fun visit(project: Project, depth: Int) {
        val kids = children[project.id].orEmpty()
        val open = project.id in expanded
        rows += ProjectRow(project, depth, kids.isNotEmpty(), open)
        if (open) kids.forEach { visit(it, depth + 1) }
    }
    tops.forEach { visit(it, 0) }
    return rows
}

/** [id]와 그 하위 프로젝트 전부의 id. */
fun projectWithDescendants(id: String, projects: List<Project>): Set<String> {
    val children = childrenByParent(projects)
    val result = mutableSetOf<String>()
    fun visit(current: String) {
        if (!result.add(current)) return
        children[current].orEmpty().forEach { visit(it.id) }
    }
    visit(id)
    return result
}

/** 부모 id별 하위 프로젝트. 부모가 목록에 없으면 최상위(null)로 본다. */
private fun childrenByParent(projects: List<Project>): Map<String?, List<Project>> {
    val ids = projects.mapTo(mutableSetOf()) { it.id }
    return projects
        .sortedBy { it.title.lowercase() }
        .groupBy { project -> project.parent?.takeIf { it in ids && it != project.id } }
}

/** 프로젝트 줄에 보일 페이지 수와 진행 중(doing/blocked) 페이지 유무. */
data class ProjectStats(val pages: Int, val active: Boolean)

/** 카드로 프로젝트별 [ProjectStats]를 센다. 하위 프로젝트의 페이지는 세지 않는다. */
fun projectStats(cards: List<PageCard>): Map<String, ProjectStats> = cards.groupBy { it.project }
    .mapValues { (_, inProject) ->
        ProjectStats(
            pages = inProject.size,
            active = inProject.any {
                it.status == PageStatus.DOING || it.status == PageStatus.BLOCKED
            }
        )
    }
