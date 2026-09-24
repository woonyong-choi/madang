package madang.shared.main

import madang.api.model.PageCard
import madang.api.model.PageStatus
import madang.api.model.Space

/** 앱 홈의 기본 공간 slug. 항상 있다. */
const val ROOT_SPACE = "root"

/** 1열 공간 트리의 한 줄. */
data class SpaceRow(
    val space: Space,
    val depth: Int,
    val hasChildren: Boolean,
    val expanded: Boolean
)

/**
 * 공간 목록을 트리 순서로 펼친다.
 *
 * 루트 공간이 맨 위, 나머지는 같은 부모 안에서 제목순이다. 접힌 공간의 하위는 빠진다.
 * [focus]가 있으면 그 공간과 하위만 보인다.
 */
fun spaceRows(spaces: List<Space>, expanded: Set<String>, focus: String? = null): List<SpaceRow> {
    val children = childrenByParent(spaces)
    val tops = if (focus != null) spaces.filter { it.slug == focus } else children[null].orEmpty()
    val rows = mutableListOf<SpaceRow>()
    fun visit(space: Space, depth: Int) {
        val kids = children[space.slug].orEmpty()
        val open = space.slug in expanded
        rows += SpaceRow(space, depth, kids.isNotEmpty(), open)
        if (open) kids.forEach { visit(it, depth + 1) }
    }
    tops.forEach { visit(it, 0) }
    return rows
}

/** [slug]와 그 하위 공간 전부의 slug. */
fun spaceWithDescendants(slug: String, spaces: List<Space>): Set<String> {
    val children = childrenByParent(spaces)
    val result = mutableSetOf<String>()
    fun visit(current: String) {
        if (!result.add(current)) return
        children[current].orEmpty().forEach { visit(it.slug) }
    }
    visit(slug)
    return result
}

/** 새 공간의 slug. 영문·숫자만 남기고 나머지는 `-`로, 겹치면 `-2`, `-3`을 붙인다. */
fun slugFor(title: String, taken: Set<String>): String {
    val base = title.lowercase()
        .map { if (it in 'a'..'z' || it in '0'..'9') it else '-' }
        .joinToString("")
        .split('-')
        .filter { it.isNotEmpty() }
        .joinToString("-")
        .ifEmpty { "space" }
    if (base !in taken) return base
    return generateSequence(2) { it + 1 }.map { "$base-$it" }.first { it !in taken }
}

/** 부모 slug별 하위 공간. 부모가 목록에 없으면 최상위(null)로 본다. */
private fun childrenByParent(spaces: List<Space>): Map<String?, List<Space>> {
    val slugs = spaces.mapTo(mutableSetOf()) { it.slug }
    return spaces
        .sortedWith(compareBy<Space> { it.slug != ROOT_SPACE }.thenBy { it.title.lowercase() })
        .groupBy { space -> space.parent?.takeIf { it in slugs && it != space.slug } }
}

/** 공간 줄에 보일 페이지 수와 진행 중(doing/blocked) 페이지 유무. */
data class SpaceStats(val pages: Int, val active: Boolean)

/** 카드로 공간별 [SpaceStats]를 센다. 하위 공간의 페이지는 세지 않는다. */
fun spaceStats(cards: List<PageCard>): Map<String, SpaceStats> = cards.groupBy { it.space }
    .mapValues { (_, inSpace) ->
        SpaceStats(
            pages = inSpace.size,
            active = inSpace.any {
                it.status == PageStatus.DOING || it.status == PageStatus.BLOCKED
            }
        )
    }
