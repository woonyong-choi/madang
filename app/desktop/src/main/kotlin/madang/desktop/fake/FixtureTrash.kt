package madang.desktop.fake

import madang.api.model.PageDetail
import madang.api.model.TrashEntry

/** 픽스처 앱 홈의 최근 삭제. 지운 페이지를 삭제 커밋 id와 함께 둔다. */
class FixtureTrash {

    private val deleted = linkedMapOf<String, Pair<TrashEntry, PageDetail>>()
    private var commits = 0

    /** 최신순 삭제 내역. */
    fun entries(): List<TrashEntry> = deleted.values.map { it.first }.reversed()

    fun add(page: PageDetail, at: String) {
        val commit = nextCommit()
        deleted[commit] = TrashEntry(
            commit = commit,
            deleted = at,
            space = page.space,
            page = page.id,
            block = null,
            paths = listOf(pagePath(page)),
            message = "[${page.id}] delete page"
        ) to page
    }

    /** 삭제 커밋이 지운 페이지를 꺼낸다. 없으면 null. */
    fun restore(commit: String): PageDetail? = deleted.remove(commit)?.second

    fun nextCommit(): String = (FIRST_COMMIT + ++commits).toString(16)

    companion object {
        private const val FIRST_COMMIT = 0x9f8e7d0

        fun pagePath(page: PageDetail) = "spaces/${page.space}/pages/${page.id}"
    }
}
