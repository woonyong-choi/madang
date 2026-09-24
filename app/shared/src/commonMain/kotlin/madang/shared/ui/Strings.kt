package madang.shared.ui

import androidx.compose.runtime.staticCompositionLocalOf
import madang.shared.core.FailureReason
import madang.shared.settings.Language

/** 화면 문구. 언어 설정에 따라 바뀐다. */
data class Strings(
    val locating: String,
    val probing: String,
    val launching: String,
    val waitingForStart: String,
    val connectFailed: String,
    val retry: String,
    val triedAddresses: String,
    val failureReason: (FailureReason?) -> String,
    val onboardingTitle: String,
    val homeStepTitle: String,
    val homeStepBody: String,
    val homeLabel: String,
    val projectStepTitle: String,
    val projectStepBody: String,
    val chooseFolder: String,
    val toolsStepTitle: String,
    val toolsStepBody: String,
    val toolNotFound: String,
    val useToolPath: String,
    val toolPathRejected: String,
    val claudeLogin: String,
    val claudeLoggedIn: (method: String?) -> String,
    val claudeLoggedOut: String,
    val recheck: String,
    val begin: String,
    val checking: String,
    val notInstalled: String,
    val available: String,
    val unavailable: String,
    val next: String,
    val settings: String,
    val close: String,
    val coreAddress: String,
    val coreAddressHint: String,
    val coreBinary: String,
    val coreBinaryHint: String,
    val connectedTo: String,
    val reconnect: String,
    val configTitle: String,
    val configHint: String,
    val projectConfigTitle: String,
    val projectConfigHint: String,
    val noProjects: String,
    val routesTitle: String,
    val save: String,
    val reload: String,
    val saving: String,
    val saved: String,
    val invalid: String,
    val runnersTitle: String,
    val refresh: String,
    val languageTitle: String,
    val eventsLive: String,
    val eventsConnecting: String,
    val eventsRetrying: String,
    val projects: String,
    val navigator: NavigatorStrings,
    val page: PageStrings,
    val tabs: TabStrings,
    val side: SideStrings
)

val KoreanStrings = Strings(
    locating = "core를 찾는 중",
    probing = "응답 확인",
    launching = "core를 띄우는 중",
    waitingForStart = "core가 준비되기를 기다리는 중",
    connectFailed = "core에 연결하지 못했습니다",
    retry = "다시 시도",
    triedAddresses = "확인한 주소",
    failureReason = {
        when (it) {
            FailureReason.NOT_RUNNING -> "실행 중인 core가 없습니다."
            FailureReason.LAUNCH_FAILED -> "core 프로세스를 시작하지 못했습니다."
            FailureReason.EXITED -> "core가 준비되기 전에 종료되었습니다."
            FailureReason.START_TIMEOUT -> "core가 제한 시간 안에 응답하지 않았습니다."
            null -> "core가 앱 홈 상태를 알려 주지 않았습니다."
        }
    },
    onboardingTitle = "Madang 시작하기",
    homeStepTitle = "전역 설정 준비",
    homeStepBody = "core가 이 폴더에 설정과 profile.md를 만듭니다. 페이지 기록은 프로젝트 폴더마다 " +
        ".madang/에 따로 둡니다.",
    homeLabel = "설정 폴더",
    projectStepTitle = "첫 프로젝트",
    projectStepBody = "작업할 폴더를 고르세요. 보통 git 저장소입니다. 페이지 기록은 그 폴더의 " +
        ".madang/에 쌓이고 기본으로 git에서 빠집니다.",
    chooseFolder = "폴더 고르기",
    toolsStepTitle = "도구 확인",
    toolsStepBody = "로그인 셸에서 claude와 codex를 찾아 그 경로를 config.yaml runners에 저장합니다. " +
        "core도 이 경로로 실행합니다. 로그인은 `claude auth status` 결과만 보며, 터미널에서 " +
        "claude로 직접 합니다.",
    toolNotFound = "찾지 못함. 실행 파일 경로를 직접 넣으세요.",
    useToolPath = "이 경로 사용",
    toolPathRejected = "실행할 수 있는 파일의 절대 경로가 아닙니다.",
    claudeLogin = "claude 로그인",
    claudeLoggedIn = { method -> "로그인됨" + (method?.let { " ($it)" } ?: "") },
    claudeLoggedOut = "로그인하지 않음. 터미널에서 claude를 실행해 로그인한 뒤 다시 확인하세요.",
    recheck = "다시 확인",
    begin = "시작",
    checking = "확인 중",
    notInstalled = "설치되지 않음",
    available = "사용 가능",
    unavailable = "사용 불가",
    next = "다음",
    settings = "설정",
    close = "닫기",
    coreAddress = "core 주소",
    coreAddressHint = "비워 두면 core.port와 기본 주소(127.0.0.1:7470)로 찾습니다.",
    coreBinary = "core 실행 파일",
    coreBinaryHint = "비워 두면 동봉된 core 또는 개발용 uv 실행을 씁니다.",
    connectedTo = "연결됨",
    reconnect = "저장하고 다시 연결",
    configTitle = "앱 설정 (config.yaml)",
    configHint = "앱 홈의 config.yaml 원문입니다. 저장하면 core가 검사하고, 에이전트는 이 파일을 받지 않습니다.",
    projectConfigTitle = "프로젝트 설정 (.madang/config.yaml)",
    projectConfigHint = "track, runs, policy, publish, viewers만 둡니다. 비어 있으면 모두 기본값입니다.",
    noProjects = "등록한 프로젝트가 없습니다.",
    routesTitle = "라우팅 표 (routes.yaml)",
    save = "저장",
    reload = "다시 불러오기",
    saving = "저장 중",
    saved = "저장했습니다",
    invalid = "core 검사에서 거부되었습니다",
    runnersTitle = "실행기",
    refresh = "새로 고침",
    languageTitle = "언어",
    eventsLive = "이벤트 연결됨",
    eventsConnecting = "이벤트 연결 중",
    eventsRetrying = "이벤트 재연결 대기",
    projects = "프로젝트",
    navigator = KoreanNavigatorStrings,
    page = KoreanPageStrings,
    tabs = KoreanTabStrings,
    side = KoreanSideStrings
)

val EnglishStrings = KoreanStrings.copy(
    locating = "Looking for core",
    probing = "Checking",
    launching = "Starting core",
    waitingForStart = "Waiting for core to be ready",
    connectFailed = "Could not connect to core",
    retry = "Retry",
    triedAddresses = "Addresses tried",
    failureReason = {
        when (it) {
            FailureReason.NOT_RUNNING -> "No core is running."
            FailureReason.LAUNCH_FAILED -> "Could not start the core process."
            FailureReason.EXITED -> "Core exited before it was ready."
            FailureReason.START_TIMEOUT -> "Core did not respond in time."
            null -> "Core did not report the app home status."
        }
    },
    onboardingTitle = "Welcome to Madang",
    homeStepTitle = "Preparing settings",
    homeStepBody = "Core creates settings and profile.md in this folder. Page records live in " +
        "each project's .madang/ folder.",
    homeLabel = "Settings folder",
    projectStepTitle = "First project",
    projectStepBody = "Choose a folder to work in, usually a git repository. Page records go to " +
        "its .madang/ folder, which git ignores by default.",
    chooseFolder = "Choose folder",
    toolsStepTitle = "Check tools",
    toolsStepBody =
        "claude and codex are looked up in your login shell and their paths are saved " +
            "to runners in config.yaml, so core runs the same files. Login is read only from " +
            "`claude auth status`; log in with claude in a terminal.",
    toolNotFound = "Not found. Enter the path to the executable.",
    useToolPath = "Use this path",
    toolPathRejected = "Not an absolute path to an executable file.",
    claudeLogin = "claude login",
    claudeLoggedIn = { method -> "Logged in" + (method?.let { " ($it)" } ?: "") },
    claudeLoggedOut = "Not logged in. Run claude in a terminal to log in, then check again.",
    recheck = "Check again",
    begin = "Start",
    checking = "Checking",
    notInstalled = "Not installed",
    available = "Available",
    unavailable = "Unavailable",
    next = "Next",
    settings = "Settings",
    close = "Close",
    coreAddress = "Core address",
    coreAddressHint = "Leave empty to use core.port and the default 127.0.0.1:7470.",
    coreBinary = "Core binary",
    coreBinaryHint = "Leave empty to use the bundled core or uv in development.",
    connectedTo = "Connected",
    reconnect = "Save and reconnect",
    configTitle = "App settings (config.yaml)",
    configHint = "The app home config.yaml. Core checks it on save; agents never receive it.",
    projectConfigTitle = "Project settings (.madang/config.yaml)",
    projectConfigHint = "Only track, runs, policy, publish and viewers. Empty means all defaults.",
    noProjects = "No projects are registered.",
    routesTitle = "Routing table (routes.yaml)",
    save = "Save",
    reload = "Reload",
    saving = "Saving",
    saved = "Saved",
    invalid = "Rejected by core validation",
    runnersTitle = "Runners",
    refresh = "Refresh",
    languageTitle = "Language",
    eventsLive = "Events live",
    eventsConnecting = "Connecting events",
    eventsRetrying = "Waiting to reconnect",
    projects = "Projects",
    navigator = EnglishNavigatorStrings,
    page = EnglishPageStrings,
    tabs = EnglishTabStrings,
    side = EnglishSideStrings
)

fun stringsFor(language: Language): Strings = when (language) {
    Language.KO -> KoreanStrings
    Language.EN -> EnglishStrings
}

val LocalStrings = staticCompositionLocalOf { KoreanStrings }
