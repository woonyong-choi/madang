package madang.shared.main

/** 레이어 0의 세 열. */
enum class Pane { SPACES, LIST, PAGE }

/** 레이어 0이 받는 키 동작. 실제 키와의 대응은 화면에서 정한다. */
enum class NavKey {
    UP,
    DOWN,
    LEFT,
    RIGHT,
    ENTER,
    BACK,
    FOCUS_SPACES,
    FOCUS_LIST,
    FOCUS_PAGE,
    NEW_PAGE
}

/** 3열을 모두 보이는 최소 폭(dp). */
const val WIDE_MIN_WIDTH = 1100f

/** 2열을 보이는 최소 폭(dp). 이보다 좁으면 1열. */
const val MEDIUM_MIN_WIDTH = 720f

/**
 * 창 폭에서 보일 열.
 *
 * 넓으면 3열, 좁으면 (공간 또는 목록) + 본문 2열, 더 좁으면 포커스가 있는 열 하나다.
 */
fun visiblePanes(widthDp: Float, focus: Pane): List<Pane> {
    val navigator = if (focus == Pane.SPACES) Pane.SPACES else Pane.LIST
    return when {
        widthDp >= WIDE_MIN_WIDTH -> Pane.entries
        widthDp >= MEDIUM_MIN_WIDTH -> listOf(navigator, Pane.PAGE)
        else -> listOf(focus)
    }
}
