package madang.shared.ui

import kotlinx.datetime.LocalDateTime
import madang.api.model.BlockType
import madang.api.model.PageStatus
import madang.api.model.SpaceSort

/** 레이어 0(공간 / 페이지 목록 / 페이지 본문) 문구. */
data class NavigatorStrings(
    val tags: String,
    val newSpace: String,
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
    val sortName: (SpaceSort) -> String,
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
    val linkRepo: String,
    val cancel: String,
    val confirm: String,
    val spaceNameLabel: String,
    val repoLabel: String,
    val tagsLabel: String,
    val tagsHint: String,
    val deletePageConfirm: (String) -> String,
    val deleteSpaceConfirm: (String) -> String,
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
    newSpace = "공간",
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
            SpaceSort.UPDATED -> "갱신순"
            SpaceSort.CREATED -> "생성순"
            SpaceSort.TITLE -> "제목순"
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
    linkRepo = "저장소 연결",
    cancel = "취소",
    confirm = "확인",
    spaceNameLabel = "공간 이름",
    repoLabel = "코드 저장소 경로",
    tagsLabel = "태그",
    tagsHint = "쉼표로 구분합니다. 하위 태그는 a/b",
    deletePageConfirm = { "'$it' 페이지를 지울까요? 최근 삭제에서 되살릴 수 있습니다." },
    deleteSpaceConfirm = { "'$it' 공간을 지울까요? 빈 공간만 지울 수 있습니다." },
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
    newSpace = "Space",
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
            SpaceSort.UPDATED -> "Updated"
            SpaceSort.CREATED -> "Created"
            SpaceSort.TITLE -> "Title"
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
    linkRepo = "Link repository",
    cancel = "Cancel",
    confirm = "OK",
    spaceNameLabel = "Space name",
    repoLabel = "Code repository path",
    tagsLabel = "Tags",
    tagsHint = "Comma separated. Nested tags use a/b",
    deletePageConfirm = { "Delete page '$it'? You can restore it from recently deleted." },
    deleteSpaceConfirm = { "Delete space '$it'? Only empty spaces can be deleted." },
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
