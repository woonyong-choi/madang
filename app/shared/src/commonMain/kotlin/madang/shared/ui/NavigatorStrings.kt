package madang.shared.ui

import kotlinx.datetime.LocalDateTime
import madang.api.model.BlockType
import madang.api.model.PageStatus
import madang.api.model.ProjectSort

/** 레이어 0(프로젝트 / 페이지 목록 / 페이지 본문) 문구. */
data class NavigatorStrings(
    val tags: String,
    val newProject: String,
    val newPage: String,
    val untitledPage: String,
    val collapseAll: String,
    val pinnedSection: String,
    val today: String,
    val yesterday: String,
    val previous7Days: String,
    val previous30Days: String,
    val month: (year: Int, month: Int) -> String,
    val year: (Int) -> String,
    val sort: String,
    val sortName: (ProjectSort) -> String,
    val filter: String,
    val clearFilter: String,
    val status: (PageStatus) -> String,
    val blockType: (BlockType) -> String,
    val cardTime: (LocalDateTime, sameDay: Boolean, sameYear: Boolean) -> String,
    val pin: String,
    val unpin: String,
    val tag: String,
    val move: String,
    val delete: String,
    val focus: String,
    val unfocus: String,
    val focused: String,
    val rename: String,
    val removeProject: String,
    val cancel: String,
    val confirm: String,
    val projectNameLabel: String,
    val chooseProjectFolder: String,
    val noProjects: String,
    val tagsLabel: String,
    val tagsHint: String,
    val deletePageConfirm: (String) -> String,
    val removeProjectConfirm: (String) -> String,
    val noPages: String,
    val noPageSelected: String,
    val expandAll: String,
    val foldByRule: String,
    val unknownFiles: (Int) -> String,
    val rows: (Int) -> String,
    val showMore: String,
    val showLess: String,
    val viewPlaceholder: String,
    val templateLabel: String,
    val inputTokens: (String) -> String,
    val outputTokens: (String) -> String,
    val seconds: (Long) -> String,
    val changedFiles: (Int) -> String,
    val running: String,
    val cancelRun: String,
    val runStarted: String,
    val runAssembled: (String) -> String,
    val runFallback: (String, String) -> String,
    val runText: String,
    val runToolCall: (String) -> String,
    val runToolResult: String,
    val runFileChanged: (String) -> String,
    val runUsage: String,
    val runDone: String,
    val runError: (String) -> String,
    val back: String,
    val dropToMove: (String) -> String,
    val dropToTag: (String) -> String
)

val KoreanNavigatorStrings = NavigatorStrings(
    tags = "태그",
    newProject = "프로젝트",
    newPage = "페이지",
    untitledPage = "제목 없음",
    collapseAll = "모두 접기",
    pinnedSection = "고정됨",
    today = "오늘",
    yesterday = "어제",
    previous7Days = "지난 7일",
    previous30Days = "지난 30일",
    month = { year, month -> "${year}년 ${month}월" },
    year = { "${it}년" },
    sort = "정렬",
    sortName = {
        when (it) {
            ProjectSort.UPDATED -> "갱신순"
            ProjectSort.CREATED -> "생성순"
            ProjectSort.TITLE -> "제목순"
        }
    },
    filter = "필터",
    clearFilter = "필터 해제",
    status = {
        when (it) {
            PageStatus.PLANNING -> "계획"
            PageStatus.DOING -> "진행"
            PageStatus.BLOCKED -> "막힘"
            PageStatus.REVIEW -> "검토"
            PageStatus.DONE -> "완료"
        }
    },
    blockType = {
        when (it) {
            BlockType.MESSAGE -> "메시지"
            BlockType.DOC -> "문서"
            BlockType.DATA -> "데이터"
            BlockType.VIEW -> "뷰"
            BlockType.CODE -> "코드"
            BlockType.TERM -> "터미널"
            BlockType.SITE -> "사이트"
            BlockType.RUN -> "실행"
        }
    },
    cardTime = { time, sameDay, sameYear ->
        val hm = "${time.hour.pad()}:${time.minute.pad()}"
        when {
            sameDay -> hm
            sameYear -> "${time.month.ordinal + 1}월 ${time.day}일"
            else -> "${time.year}. ${time.month.ordinal + 1}. ${time.day}."
        }
    },
    pin = "고정",
    unpin = "고정 해제",
    tag = "태그",
    move = "이동",
    delete = "삭제",
    focus = "포커스",
    unfocus = "포커스 해제",
    focused = "포커스",
    rename = "이름 변경",
    removeProject = "등록 해제",
    cancel = "취소",
    confirm = "확인",
    projectNameLabel = "프로젝트 이름",
    chooseProjectFolder = "프로젝트로 쓸 폴더 고르기",
    noProjects = "프로젝트가 없습니다. 폴더를 추가하세요.",
    tagsLabel = "태그",
    tagsHint = "쉼표로 구분합니다. 하위 태그는 a/b",
    deletePageConfirm = { "'$it' 페이지를 지울까요? 최근 삭제에서 되살릴 수 있습니다." },
    removeProjectConfirm = {
        "'$it' 프로젝트 등록을 해제할까요? 폴더와 그 안의 .madang 기록은 그대로 남습니다."
    },
    noPages = "페이지가 없습니다",
    noPageSelected = "페이지를 고르세요",
    expandAll = "모두 펼치기",
    foldByRule = "기본 접힘",
    unknownFiles = { "등록되지 않은 파일 ${it}개" },
    rows = { "${it}행" },
    showMore = "더 보기",
    showLess = "줄이기",
    viewPlaceholder = "템플릿 화면 미리보기는 아직 지원하지 않습니다.",
    templateLabel = "템플릿",
    inputTokens = { "입력 $it" },
    outputTokens = { "출력 $it" },
    seconds = { if (it >= 60) "${it / 60}분 ${it % 60}초" else "${it}초" },
    changedFiles = { "파일 ${it}개" },
    running = "실행 중",
    cancelRun = "취소",
    runStarted = "시작했습니다",
    runAssembled = { "입력 조립 ~$it" },
    runFallback = { from, to -> "대체: $from → $to" },
    runText = "응답 작성 중",
    runToolCall = { "도구 호출 $it" },
    runToolResult = "도구 결과",
    runFileChanged = { "파일 변경 $it" },
    runUsage = "토큰 집계",
    runDone = "마무리 중",
    runError = { "오류 $it" },
    back = "뒤로",
    dropToMove = { "'$it'(으)로 이동" },
    dropToTag = { "#$it 태그 추가" }
)

val EnglishNavigatorStrings = KoreanNavigatorStrings.copy(
    tags = "Tags",
    newProject = "Project",
    newPage = "Page",
    untitledPage = "Untitled",
    collapseAll = "Collapse all",
    pinnedSection = "Pinned",
    today = "Today",
    yesterday = "Yesterday",
    previous7Days = "Previous 7 days",
    previous30Days = "Previous 30 days",
    month = { year, month -> "$year-${month.pad()}" },
    year = { "$it" },
    sort = "Sort",
    sortName = {
        when (it) {
            ProjectSort.UPDATED -> "Updated"
            ProjectSort.CREATED -> "Created"
            ProjectSort.TITLE -> "Title"
        }
    },
    filter = "Filter",
    clearFilter = "Clear filter",
    status = { it.value },
    blockType = { it.value },
    cardTime = { time, sameDay, sameYear ->
        val hm = "${time.hour.pad()}:${time.minute.pad()}"
        when {
            sameDay -> hm
            sameYear -> "${time.month.ordinal + 1}/${time.day}"
            else -> "${time.year}-${(time.month.ordinal + 1).pad()}-${time.day.pad()}"
        }
    },
    pin = "Pin",
    unpin = "Unpin",
    tag = "Tag",
    move = "Move",
    delete = "Delete",
    focus = "Focus",
    unfocus = "Unfocus",
    focused = "Focus",
    rename = "Rename",
    removeProject = "Remove",
    cancel = "Cancel",
    confirm = "OK",
    projectNameLabel = "Project name",
    chooseProjectFolder = "Choose a folder for the project",
    noProjects = "No projects yet. Add a folder.",
    tagsLabel = "Tags",
    tagsHint = "Comma separated. Nested tags use a/b",
    deletePageConfirm = { "Delete page '$it'? You can restore it from recently deleted." },
    removeProjectConfirm = {
        "Remove project '$it'? The folder and its .madang records stay on disk."
    },
    noPages = "No pages",
    noPageSelected = "Select a page",
    expandAll = "Expand all",
    foldByRule = "Default folding",
    unknownFiles = { "$it unregistered files" },
    rows = { "$it rows" },
    showMore = "Show more",
    showLess = "Show less",
    viewPlaceholder = "Template previews are not supported yet.",
    templateLabel = "Template",
    inputTokens = { "in $it" },
    outputTokens = { "out $it" },
    seconds = { if (it >= 60) "${it / 60}m ${it % 60}s" else "${it}s" },
    changedFiles = { "$it files" },
    running = "Running",
    cancelRun = "Cancel",
    runStarted = "Started",
    runAssembled = { "Input assembled ~$it" },
    runFallback = { from, to -> "Fallback: $from → $to" },
    runText = "Writing",
    runToolCall = { "Tool call $it" },
    runToolResult = "Tool result",
    runFileChanged = { "Changed $it" },
    runUsage = "Counting tokens",
    runDone = "Finishing",
    runError = { "Error $it" },
    back = "Back",
    dropToMove = { "Move to '$it'" },
    dropToTag = { "Add #$it" }
)

private fun Int.pad(): String = toString().padStart(2, '0')
