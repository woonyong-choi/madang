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
    val openSettingsHint: String,
    val triedAddresses: String,
    val failureReason: (FailureReason?) -> String,
    val onboardingTitle: String,
    val homeStepTitle: String,
    val homeStepBody: String,
    val remoteStepTitle: String,
    val remoteStepBody: String,
    val remoteInvalid: String,
    val toolsStepTitle: String,
    val toolsStepBody: String,
    val checking: String,
    val notInstalled: String,
    val coreRunners: String,
    val available: String,
    val unavailable: String,
    val permissionsStepTitle: String,
    val permissionsStepBody: String,
    val permissionsNote: String,
    val back: String,
    val next: String,
    val later: String,
    val settings: String,
    val close: String,
    val coreAddress: String,
    val coreAddressHint: String,
    val coreBinary: String,
    val coreBinaryHint: String,
    val connectedTo: String,
    val reconnect: String,
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
    val spaces: String,
    val recentEvents: String,
    val noEvents: String
)

val KoreanStrings = Strings(
    locating = "core를 찾는 중",
    probing = "응답 확인",
    launching = "core를 띄우는 중",
    waitingForStart = "core가 준비되기를 기다리는 중",
    connectFailed = "core에 연결하지 못했습니다",
    retry = "다시 시도",
    openSettingsHint = "core 주소나 실행 파일 경로는 앱 설정 파일에서 바꿀 수 있습니다.",
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
    homeStepTitle = "앱 홈 위치",
    homeStepBody = "페이지와 설정을 담을 폴더입니다. core가 이 위치에 git 저장소로 만듭니다.",
    remoteStepTitle = "원격 저장소 (선택)",
    remoteStepBody = "앱 홈을 백업할 git 원격 주소입니다. 저장소를 만들지는 않고 주소만 기록합니다.",
    remoteInvalid = "https://, ssh:// 또는 git@host:path 형식이어야 합니다.",
    toolsStepTitle = "에이전트 도구 확인",
    toolsStepBody = "claude와 codex CLI가 설치되어 있는지 봅니다. 로그인은 각 도구에서 직접 합니다.",
    checking = "확인 중",
    notInstalled = "설치되지 않음",
    coreRunners = "core가 본 사용 가능 여부",
    available = "사용 가능",
    unavailable = "사용 불가",
    permissionsStepTitle = "권한 규칙 제안",
    permissionsStepBody = "에이전트가 madang 명령만 자유롭게 쓰고 위험한 명령은 막도록 아래 규칙을 권합니다.",
    permissionsNote = "지금은 파일을 바꾸지 않습니다. 규칙 추가는 이후 버전에서 승인을 받은 뒤 적용합니다.",
    back = "이전",
    next = "다음",
    later = "나중에",
    settings = "설정",
    close = "닫기",
    coreAddress = "core 주소",
    coreAddressHint = "비워 두면 core.port와 기본 주소(127.0.0.1:7470)로 찾습니다.",
    coreBinary = "core 실행 파일",
    coreBinaryHint = "비워 두면 동봉된 core 또는 개발용 uv 실행을 씁니다.",
    connectedTo = "연결됨",
    reconnect = "저장하고 다시 연결",
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
    spaces = "공간",
    recentEvents = "최근 이벤트",
    noEvents = "아직 이벤트가 없습니다"
)

val EnglishStrings = KoreanStrings.copy(
    locating = "Looking for core",
    probing = "Checking",
    launching = "Starting core",
    waitingForStart = "Waiting for core to be ready",
    connectFailed = "Could not connect to core",
    retry = "Retry",
    openSettingsHint = "The core address and binary path live in the app settings file.",
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
    homeStepTitle = "App home location",
    homeStepBody = "The folder for pages and settings. Core creates it as a git repository.",
    remoteStepTitle = "Remote repository (optional)",
    remoteStepBody = "A git remote for backing up the app home. Only the address is recorded.",
    remoteInvalid = "Use https://, ssh:// or git@host:path.",
    toolsStepTitle = "Agent tools",
    toolsStepBody = "Checks that the claude and codex CLIs are installed. Log in from each tool.",
    checking = "Checking",
    notInstalled = "Not installed",
    coreRunners = "Availability reported by core",
    available = "Available",
    unavailable = "Unavailable",
    permissionsStepTitle = "Suggested permission rules",
    permissionsStepBody = "These rules let agents run madang commands and block risky ones.",
    permissionsNote = "No files are changed now. Rules are added later, after your approval.",
    back = "Back",
    next = "Next",
    later = "Later",
    settings = "Settings",
    close = "Close",
    coreAddress = "Core address",
    coreAddressHint = "Leave empty to use core.port and the default 127.0.0.1:7470.",
    coreBinary = "Core binary",
    coreBinaryHint = "Leave empty to use the bundled core or uv in development.",
    connectedTo = "Connected",
    reconnect = "Save and reconnect",
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
    spaces = "Spaces",
    recentEvents = "Recent events",
    noEvents = "No events yet"
)

fun stringsFor(language: Language): Strings = when (language) {
    Language.KO -> KoreanStrings
    Language.EN -> EnglishStrings
}

val LocalStrings = staticCompositionLocalOf { KoreanStrings }
