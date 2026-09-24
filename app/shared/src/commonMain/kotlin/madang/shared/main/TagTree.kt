package madang.shared.main

import madang.api.model.PageCard

/** 1열 태그 트리의 한 줄. [path]는 `a/b` 형식의 전체 태그다. */
data class TagRow(
    val path: String,
    val name: String,
    val depth: Int,
    val count: Int,
    val hasChildren: Boolean,
    val expanded: Boolean
)

/**
 * 페이지 태그로 계층 태그 트리를 만든다.
 *
 * `a/b` 태그는 `a` 아래의 `b`다. 개수는 그 태그나 하위 태그를 가진 페이지 수다.
 * 접힌 태그의 하위는 빠진다.
 */
fun tagRows(cards: Collection<PageCard>, expanded: Set<String>): List<TagRow> {
    val paths = cards.flatMap { it.tags }.flatMap(::tagPrefixes).toSortedSet()
    val children = paths.groupBy { it.substringBeforeLast('/', missingDelimiterValue = "") }
    val rows = mutableListOf<TagRow>()
    fun visit(path: String, depth: Int) {
        val kids = children[path].orEmpty()
        val open = path in expanded
        val count = cards.count { card -> card.tags.any { tagMatches(it, path) } }
        rows += TagRow(path, path.substringAfterLast('/'), depth, count, kids.isNotEmpty(), open)
        if (open) kids.forEach { visit(it, depth + 1) }
    }
    children[""].orEmpty().forEach { visit(it, 0) }
    return rows
}

/** [tag]가 [filter] 자신이거나 그 하위 태그인가. */
fun tagMatches(tag: String, filter: String): Boolean = tag == filter || tag.startsWith("$filter/")

/** `a/b/c` → `a`, `a/b`, `a/b/c`. */
private fun tagPrefixes(tag: String): List<String> {
    val parts = tag.trim('/').split('/').filter { it.isNotEmpty() }
    return parts.indices.map { parts.subList(0, it + 1).joinToString("/") }
}
