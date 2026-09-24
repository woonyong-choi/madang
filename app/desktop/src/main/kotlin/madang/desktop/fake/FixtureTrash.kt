package madang.desktop.fake

import madang.api.model.PageDetail
import madang.api.model.TrashEntry

/** 픽스처의 최근 삭제. 지운 페이지를 core처럼 `<시각>-page` 꼴의 휴지통 항목 id와 함께 둔다. */
class FixtureTrash {

    private val deleted = linkedMapOf<String, Pair<TrashEntry, PageDetail>>()
    private var count = 0

    /** 최신순 삭제 내역. */
    fun entries(): List<TrashEntry> = deleted.values.map { it.first }.reversed()

    fun add(page: PageDetail, at: String) {
        val id = "20260924T100000%06d-page".format(++count)
        deleted[id] = TrashEntry(
            id = id,
            deleted = at,
            project = page.project,
            page = page.id,
            block = null,
            paths = listOf(pagePath(page))
        ) to page
    }

    /** 휴지통 항목의 페이지를 꺼낸다. 없으면 null. */
    fun restore(id: String): PageDetail? = deleted.remove(id)?.second

    companion object {
        /** 프로젝트 폴더 기준 페이지 경로. */
        fun pagePath(page: PageDetail) = ".madang/pages/${page.id}"
    }
}
