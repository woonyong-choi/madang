package madang.shared.main

/** 키 처리 뒤 ViewModel이 할 일. */
sealed interface KeyEffect {
    data class OpenPage(val id: String) : KeyEffect

    data object NewPage : KeyEffect
}

data class KeyOutcome(val state: MainState, val effect: KeyEffect? = null)

/**
 * 레이어 0 키보드 탐색.
 *
 * - 공간 열: 위아래로 공간·태그를 고른다(목록이 바로 바뀐다). 오른쪽은 접힌 항목을 펼치고,
 *   펼쳐져 있거나 하위가 없으면 목록 열로 간다. 왼쪽은 펼친 항목을 접고, 접혀 있으면
 *   상위로 간다. Enter는 목록 열로 간다.
 * - 목록 열: 위아래로 페이지를 고르고 연다. 오른쪽·Enter는 본문 열로, 왼쪽·Backspace는
 *   공간 열로 간다.
 * - 본문 열: 왼쪽·Backspace는 목록 열로 간다.
 */
fun MainState.onKey(key: NavKey): KeyOutcome = when (key) {
    NavKey.FOCUS_SPACES -> KeyOutcome(copy(pane = Pane.SPACES))

    NavKey.FOCUS_LIST -> KeyOutcome(copy(pane = Pane.LIST))

    NavKey.FOCUS_PAGE -> KeyOutcome(copy(pane = Pane.PAGE))

    NavKey.NEW_PAGE -> KeyOutcome(this, KeyEffect.NewPage)

    else -> when (pane) {
        Pane.SPACES -> spacesKey(key)
        Pane.LIST -> listKey(key)
        Pane.PAGE -> pageKey(key)
    }
}

private fun MainState.spacesKey(key: NavKey): KeyOutcome = when (key) {
    NavKey.UP -> KeyOutcome(copy(source = step(navItems, source, -1)))
    NavKey.DOWN -> KeyOutcome(copy(source = step(navItems, source, +1)))
    NavKey.RIGHT -> expandOrEnterList()
    NavKey.LEFT -> KeyOutcome(collapseOrGoUp())
    NavKey.ENTER -> enterList()
    else -> KeyOutcome(this)
}

private fun MainState.listKey(key: NavKey): KeyOutcome = when (key) {
    NavKey.UP, NavKey.DOWN -> {
        val ids = listCards.map { it.id }
        val next = step(ids, selectedPage, if (key == NavKey.UP) -1 else +1)
        if (next == null || next == selectedPage) {
            KeyOutcome(this)
        } else {
            KeyOutcome(copy(selectedPage = next), KeyEffect.OpenPage(next))
        }
    }

    NavKey.RIGHT, NavKey.ENTER ->
        KeyOutcome(if (selectedPage != null) copy(pane = Pane.PAGE) else this)

    NavKey.LEFT, NavKey.BACK -> KeyOutcome(copy(pane = Pane.SPACES))

    else -> KeyOutcome(this)
}

private fun MainState.pageKey(key: NavKey): KeyOutcome = when (key) {
    NavKey.LEFT, NavKey.BACK -> KeyOutcome(copy(pane = Pane.LIST))
    else -> KeyOutcome(this)
}

private fun MainState.expandOrEnterList(): KeyOutcome {
    when (val current = source) {
        is ListSource.InSpace -> {
            val row = spaceRows.firstOrNull { it.space.slug == current.slug }
            if (row != null && row.hasChildren && !row.expanded) {
                return KeyOutcome(copy(expandedSpaces = expandedSpaces + current.slug))
            }
        }

        is ListSource.WithTag -> {
            val row = tagRows.firstOrNull { it.path == current.path }
            if (row != null && row.hasChildren && !row.expanded) {
                return KeyOutcome(copy(expandedTags = expandedTags + current.path))
            }
        }

        null -> Unit
    }
    return enterList()
}

private fun MainState.collapseOrGoUp(): MainState = when (val current = source) {
    is ListSource.InSpace -> when {
        current.slug in expandedSpaces -> copy(expandedSpaces = expandedSpaces - current.slug)

        else -> spaces.firstOrNull { it.slug == current.slug }?.parent
            ?.takeIf { parent -> spaceRows.any { it.space.slug == parent } }
            ?.let { copy(source = ListSource.InSpace(it)) }
            ?: this
    }

    is ListSource.WithTag -> when {
        current.path in expandedTags -> copy(expandedTags = expandedTags - current.path)

        '/' in current.path -> copy(
            source = ListSource.WithTag(current.path.substringBeforeLast('/'))
        )

        else -> this
    }

    null -> this
}

/** 목록 열로 간다. 고른 페이지가 목록에 없으면 첫 페이지를 고르고 연다. */
private fun MainState.enterList(): KeyOutcome {
    val cards = listCards
    if (cards.any { it.id == selectedPage }) return KeyOutcome(copy(pane = Pane.LIST))
    val first = cards.firstOrNull() ?: return KeyOutcome(copy(pane = Pane.LIST))
    return KeyOutcome(
        copy(pane = Pane.LIST, selectedPage = first.id),
        KeyEffect.OpenPage(first.id)
    )
}

/** [items]에서 [current]의 이웃. [current]가 없으면 첫 항목. 끝에서는 멈춘다. */
private fun <T> step(items: List<T>, current: T?, delta: Int): T? {
    if (items.isEmpty()) return current
    val index = items.indexOf(current)
    if (index < 0) return items.first()
    return items[(index + delta).coerceIn(0, items.lastIndex)]
}
