package madang.shared.main

/** 오른쪽 사이드바의 탭. 선언 순서가 화면 순서다. */
enum class SideTab { NOW, FILES, MEMORY, GIT, PORTS, HISTORY }

/** 오른쪽 사이드바. [open]이면 가운데 열 오른쪽에 붙어 [tab]을 보인다. */
data class Sidebar(val open: Boolean = false, val tab: SideTab = SideTab.MEMORY) {
    val showsMemory: Boolean get() = open && tab == SideTab.MEMORY
}
