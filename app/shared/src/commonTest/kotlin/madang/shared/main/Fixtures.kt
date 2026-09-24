package madang.shared.main

import madang.api.model.PageCard
import madang.api.model.PageStatus
import madang.api.model.Space
import madang.api.model.SpaceSort

fun space(slug: String, title: String = slug, parent: String? = null, sort: SpaceSort? = null) =
    Space(slug = slug, title = title, parent = parent, sort = sort)

fun card(
    id: String,
    space: String = ROOT_SPACE,
    title: String = id,
    status: PageStatus = PageStatus.PLANNING,
    pinned: Boolean = false,
    tags: List<String> = emptyList(),
    updated: String? = null,
    created: String? = null
) = PageCard(
    id = id,
    space = space,
    title = title,
    status = status,
    pinned = pinned,
    tags = tags,
    blockCounts = emptyMap(),
    updated = updated,
    created = created
)

/** 루트, 지원(하위: 2026 하반기), 블로그 공간과 그 페이지들. */
object Home {
    val spaces = listOf(
        space(ROOT_SPACE, "루트"),
        space("jobs", "지원"),
        space("jobs-2026", "2026 하반기", parent = "jobs", sort = SpaceSort.TITLE),
        space("blog", "블로그", sort = SpaceSort.CREATED)
    )

    val resume = card(
        "resume",
        "jobs",
        "이력서",
        PageStatus.DOING,
        pinned = true,
        tags = listOf("이력서"),
        updated = "2026-09-24T09:31:41+09:00",
        created = "2026-09-20T08:00:00+09:00"
    )
    val posting = card(
        "posting",
        "jobs",
        "공고 분석",
        PageStatus.REVIEW,
        tags = listOf("이력서/공고"),
        updated = "2026-09-23T18:00:00+09:00",
        created = "2026-09-23T08:00:00+09:00"
    )
    val cover = card(
        "cover",
        "jobs-2026",
        "자기소개서",
        PageStatus.DONE,
        updated = "2026-09-24T10:00:00+09:00",
        created = "2026-09-01T08:00:00+09:00"
    )
    val draft = card(
        "draft",
        "blog",
        "가비지 컬렉터",
        PageStatus.BLOCKED,
        tags = listOf("글"),
        updated = "2026-08-10T12:00:00+09:00",
        created = "2026-09-22T12:00:00+09:00"
    )

    val cards = listOf(resume, posting, cover, draft)

    fun state(pane: Pane = Pane.SPACES) = MainState(baseUrl = "http://core")
        .withLoaded(spaces, cards)
        .copy(pane = pane)
}
