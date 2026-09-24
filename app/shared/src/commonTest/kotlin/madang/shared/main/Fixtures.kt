package madang.shared.main

import madang.api.model.PageCard
import madang.api.model.PageStatus
import madang.api.model.Project
import madang.api.model.ProjectSort

/** 테스트 프로젝트. 폴더 경로는 `/work/<id>`. */
fun project(id: String, title: String = id, parent: String? = null, sort: ProjectSort? = null) =
    Project(id = id, title = title, path = "/work/$id", parent = parent, sort = sort)

/** 하위 프로젝트가 없고 제목순으로 맨 앞에 오는 테스트 프로젝트. */
const val NOTES = "notes"

fun card(
    id: String,
    project: String = NOTES,
    title: String = id,
    status: PageStatus = PageStatus.PLANNING,
    pinned: Boolean = false,
    tags: List<String> = emptyList(),
    updated: String? = null,
    created: String? = null
) = PageCard(
    id = id,
    project = project,
    title = title,
    status = status,
    pinned = pinned,
    tags = tags,
    blockCounts = emptyMap(),
    updated = updated,
    created = created
)

/** 노트, 지원(하위: 2026 하반기), 블로그 프로젝트와 그 페이지들. */
object Home {
    val projects = listOf(
        project(NOTES, "노트"),
        project("jobs", "지원"),
        project("jobs-2026", "2026 하반기", parent = "jobs", sort = ProjectSort.TITLE),
        project("blog", "블로그", sort = ProjectSort.CREATED)
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

    fun state(pane: Pane = Pane.PROJECTS) = MainState(baseUrl = "http://core")
        .withLoaded(projects, cards)
        .copy(pane = pane)
}
