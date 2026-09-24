package madang.shared.ui

import madang.api.model.FileLens
import madang.api.model.UsageWindow
import madang.shared.main.Notice
import madang.shared.main.RunGlyph

/** 오른쪽 사이드바의 지금 · 파일 · git · 포트 · 기록 탭과 시스템 알림 문구. */
data class SideStrings(
    val glyph: (RunGlyph) -> String,
    val loading: String,
    val failed: (String?) -> String,
    val reload: String,
    val noProject: String,
    val usageTitle: String,
    val usageWindow: (UsageWindow.Name) -> String,
    val usageTokens: (String) -> String,
    val usageWarn: String,
    val usageNoRecords: String,
    val nowTitle: String,
    val nowEmpty: String,
    val showLog: String,
    val hideLog: String,
    val noEvents: String,
    val inputTitle: (Int) -> String,
    val inputNotRecorded: String,
    val inputTotal: String,
    val lens: (FileLens) -> String,
    val runBadge: String,
    val filesEmpty: String,
    val filesTruncated: String,
    val notRepository: String,
    val gitNotRepository: String,
    val gitInit: String,
    val gitChanges: String,
    val gitStaged: String,
    val gitStage: String,
    val gitStageAll: String,
    val gitNoChanges: String,
    val gitCommitPlaceholder: String,
    val gitCommit: String,
    val gitPush: String,
    val gitPull: String,
    val gitBranches: String,
    val gitDetached: String,
    val gitWorktrees: String,
    val gitWorktreeMain: String,
    val gitWorktreePage: (String) -> String,
    val gitLog: String,
    val portsEmpty: String,
    val portDeclared: (String) -> String,
    val portDeclare: String,
    val portNamePlaceholder: String,
    val save: String,
    val cancel: String,
    val historyNoPage: String,
    val historyEmpty: String,
    val historyCost: (input: String, output: String) -> String,
    val noticeTitle: (Notice) -> String,
    val noticeBody: (Notice) -> String,
    val notificationsTitle: String,
    val notificationsLabel: String
)

val KoreanSideStrings = SideStrings(
    glyph = {
        when (it) {
            RunGlyph.RUNNING -> "실행 중"
            RunGlyph.NEEDS_HUMAN -> "사람 필요"
            RunGlyph.DONE -> "완료"
            RunGlyph.FAILED -> "실패"
            RunGlyph.IDLE -> "유휴"
        }
    },
    loading = "불러오는 중",
    failed = { "불러오지 못했습니다${it?.let { m -> ": $m" }.orEmpty()}" },
    reload = "새로 고침",
    noProject = "프로젝트를 고르면 보입니다.",
    usageTitle = "사용량",
    usageWindow = {
        when (it) {
            UsageWindow.Name._5H -> "5시간"
            UsageWindow.Name.WEEK -> "7일"
        }
    },
    usageTokens = { "$it 토큰" },
    usageWarn = "80% 이상",
    usageNoRecords = "사용 기록 없음",
    nowTitle = "진행 중 · 최근 30분",
    nowEmpty = "진행 중이거나 최근 30분 안에 끝난 실행이 없습니다.",
    showLog = "로그",
    hideLog = "로그 접기",
    noEvents = "이벤트 없음",
    inputTitle = { "run $it 입력 구성" },
    inputNotRecorded = "입력 구성이 기록되지 않았습니다.",
    inputTotal = "합계",
    lens = {
        when (it) {
            FileLens.ALL -> "전체"
            FileLens.PAGE -> "이 페이지"
            FileLens.CHANGED -> "변경됨"
        }
    },
    runBadge = "실행",
    filesEmpty = "파일이 없습니다.",
    filesTruncated = "항목이 많아 일부만 보입니다.",
    notRepository = "git 저장소가 아니라 변경을 볼 수 없습니다.",
    gitNotRepository = "이 프로젝트는 git 저장소가 아닙니다.",
    gitInit = "git 시작",
    gitChanges = "변경",
    gitStaged = "스테이지됨",
    gitStage = "스테이지",
    gitStageAll = "모두 스테이지",
    gitNoChanges = "변경 없음",
    gitCommitPlaceholder = "커밋 메시지",
    gitCommit = "커밋",
    gitPush = "푸시",
    gitPull = "풀",
    gitBranches = "브랜치",
    gitDetached = "(분리된 HEAD)",
    gitWorktrees = "워크트리",
    gitWorktreeMain = "메인 체크아웃",
    gitWorktreePage = { "페이지: $it" },
    gitLog = "로그",
    portsEmpty = "관찰된 열린 포트가 없습니다.",
    portDeclared = { "선언: $it" },
    portDeclare = "선언으로 저장",
    portNamePlaceholder = "실행 대상 이름",
    save = "저장",
    cancel = "취소",
    historyNoPage = "페이지를 열면 그 페이지의 실행 기록이 보입니다.",
    historyEmpty = "실행 기록이 없습니다.",
    historyCost = { input, output -> "입력 $input · 출력 $output" },
    noticeTitle = {
        when (it) {
            is Notice.Finished -> "완료: ${it.title}"
            is Notice.Failed -> "실패: ${it.title}"
            is Notice.Asked -> "답이 필요합니다: ${it.title}"
        }
    },
    noticeBody = {
        when (it) {
            is Notice.Finished -> "run이 끝났습니다${it.status?.let { s -> " ($s)" }.orEmpty()}."
            is Notice.Failed -> it.error
            is Notice.Asked -> it.prompt
        }
    },
    notificationsTitle = "알림",
    notificationsLabel = "run 완료·실패와 묻는 블록을 시스템 알림으로 알리기"
)

val EnglishSideStrings = KoreanSideStrings.copy(
    glyph = {
        when (it) {
            RunGlyph.RUNNING -> "Running"
            RunGlyph.NEEDS_HUMAN -> "Needs you"
            RunGlyph.DONE -> "Done"
            RunGlyph.FAILED -> "Failed"
            RunGlyph.IDLE -> "Idle"
        }
    },
    loading = "Loading",
    failed = { "Could not load${it?.let { m -> ": $m" }.orEmpty()}" },
    reload = "Reload",
    noProject = "Choose a project to see this.",
    usageTitle = "Usage",
    usageWindow = {
        when (it) {
            UsageWindow.Name._5H -> "5 hours"
            UsageWindow.Name.WEEK -> "7 days"
        }
    },
    usageTokens = { "$it tokens" },
    usageWarn = "80% or more",
    usageNoRecords = "No usage records",
    nowTitle = "Running · last 30 minutes",
    nowEmpty = "Nothing is running or finished in the last 30 minutes.",
    showLog = "Log",
    hideLog = "Hide log",
    noEvents = "No events",
    inputTitle = { "Run $it input" },
    inputNotRecorded = "The input was not recorded.",
    inputTotal = "Total",
    lens = {
        when (it) {
            FileLens.ALL -> "All"
            FileLens.PAGE -> "This page"
            FileLens.CHANGED -> "Changed"
        }
    },
    runBadge = "Run",
    filesEmpty = "No files.",
    filesTruncated = "Too many entries; showing some.",
    notRepository = "Not a git repository, so there are no changes to show.",
    gitNotRepository = "This project is not a git repository.",
    gitInit = "Start git",
    gitChanges = "Changes",
    gitStaged = "Staged",
    gitStage = "Stage",
    gitStageAll = "Stage all",
    gitNoChanges = "No changes",
    gitCommitPlaceholder = "Commit message",
    gitCommit = "Commit",
    gitPush = "Push",
    gitPull = "Pull",
    gitBranches = "Branches",
    gitDetached = "(detached HEAD)",
    gitWorktrees = "Worktrees",
    gitWorktreeMain = "Main checkout",
    gitWorktreePage = { "Page: $it" },
    gitLog = "Log",
    portsEmpty = "No open ports observed.",
    portDeclared = { "Declared: $it" },
    portDeclare = "Save as declaration",
    portNamePlaceholder = "Run target name",
    save = "Save",
    cancel = "Cancel",
    historyNoPage = "Open a page to see its runs.",
    historyEmpty = "No runs yet.",
    historyCost = { input, output -> "in $input · out $output" },
    noticeTitle = {
        when (it) {
            is Notice.Finished -> "Done: ${it.title}"
            is Notice.Failed -> "Failed: ${it.title}"
            is Notice.Asked -> "Needs an answer: ${it.title}"
        }
    },
    noticeBody = {
        when (it) {
            is Notice.Finished -> "The run finished${it.status?.let { s -> " ($s)" }.orEmpty()}."
            is Notice.Failed -> it.error
            is Notice.Asked -> it.prompt
        }
    },
    notificationsTitle = "Notifications",
    notificationsLabel = "Notify when a run finishes or fails and when a page asks"
)
