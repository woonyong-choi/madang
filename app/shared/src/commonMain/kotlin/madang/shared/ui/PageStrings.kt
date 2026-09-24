package madang.shared.ui

import madang.api.model.MemoryLayer
import madang.api.model.UnknownFileAction
import madang.shared.main.SideTab

/** 입력창, 오른쪽 사이드바와 메모리 탭, 미등록 파일, 사람 결정, 최근 삭제, 페이지 검색 문구. */
data class PageStrings(
    val toPage: String,
    val inputPlaceholder: String,
    val send: String,
    val sending: String,
    val nextInput: (tokens: String, runner: String) -> String,
    val completeHint: String,
    val memory: String,
    val memoryLayer: (MemoryLayer) -> String,
    val memoryTokens: (tokens: Int, limit: Int?) -> String,
    val memoryLoading: String,
    val memorySaved: String,
    val memoryRejected: (Int) -> String,
    val memoryRaw: String,
    val memoryNoPage: String,
    val memoryEmptyBody: String,
    val sideTab: (SideTab) -> String,
    val sideTabPending: String,
    val lineLabel: (Int) -> String,
    val unknownFilesTitle: String,
    val unknownFileRun: (Int) -> String,
    val unknownFileAction: (UnknownFileAction.Action) -> String,
    val decisionTitle: String,
    val decisionSent: String,
    val yes: String,
    val no: String,
    val waitingReason: (String) -> String,
    val recentlyDeleted: String,
    val trashEmpty: String,
    val trashPage: String,
    val trashBlock: (String) -> String,
    val restore: String,
    val searchTitle: String,
    val searchPlaceholder: String,
    val searchEmpty: String,
    val close: String
)

val KoreanPageStrings = PageStrings(
    toPage = "페이지에게",
    inputPlaceholder = "요청을 적으세요 (Enter 보내기, Shift+Enter 줄바꿈)",
    send = "보내기",
    sending = "보내는 중",
    nextInput = { tokens, runner -> "~$tokens · $runner" },
    completeHint = "Tab 자동완성",
    memory = "메모리",
    memoryLayer = {
        when (it) {
            MemoryLayer.PROFILE -> "Profile"
            MemoryLayer.BRIEF -> "Brief"
            MemoryLayer.LEDGER -> "Ledger"
        }
    },
    memoryTokens = { tokens, limit -> if (limit != null) "$tokens / $limit 토큰" else "$tokens 토큰" },
    memoryLoading = "불러오는 중",
    memorySaved = "저장했습니다",
    memoryRejected = { "core 검사에서 거부되었습니다 (${it}건)" },
    memoryRaw = "원문",
    memoryNoPage = "페이지를 열면 그 페이지가 쓰는 Profile / Brief / Ledger가 보입니다.",
    memoryEmptyBody = "(본문 없음)",
    sideTab = {
        when (it) {
            SideTab.NOW -> "지금"
            SideTab.FILES -> "파일"
            SideTab.MEMORY -> "메모리"
            SideTab.GIT -> "git"
            SideTab.PORTS -> "포트"
            SideTab.HISTORY -> "기록"
        }
    },
    sideTabPending = "이 탭은 아직 비어 있습니다.",
    lineLabel = { "${it}행" },
    unknownFilesTitle = "등록되지 않은 파일",
    unknownFileRun = { "run $it" },
    unknownFileAction = {
        when (it) {
            UnknownFileAction.Action.ARTIFACT -> "산출물로"
            UnknownFileAction.Action.KEEP -> "유지"
            UnknownFileAction.Action.DELETE -> "삭제"
        }
    },
    decisionTitle = "결정이 필요합니다",
    decisionSent = "답을 보냈습니다. 흐름이 다시 시작되기를 기다립니다.",
    yes = "예",
    no = "아니오",
    waitingReason = {
        when (it) {
            "no_runner" -> "쓸 수 있는 실행기가 없어 흐름이 멈췄습니다. 설정에서 실행기를 확인하세요."
            else -> "흐름이 기다리는 중입니다: $it"
        }
    },
    recentlyDeleted = "최근 삭제",
    trashEmpty = "최근 삭제한 것이 없습니다",
    trashPage = "페이지",
    trashBlock = { "블록 $it" },
    restore = "복구",
    searchTitle = "페이지 검색",
    searchPlaceholder = "제목, 내용, #태그",
    searchEmpty = "맞는 페이지가 없습니다",
    close = "닫기"
)

val EnglishPageStrings = KoreanPageStrings.copy(
    toPage = "To page",
    inputPlaceholder = "Write a request (Enter to send, Shift+Enter for a new line)",
    send = "Send",
    sending = "Sending",
    completeHint = "Tab to complete",
    memory = "Memory",
    memoryTokens = { tokens, limit ->
        if (limit != null) "$tokens / $limit tokens" else "$tokens tokens"
    },
    memoryLoading = "Loading",
    memorySaved = "Saved",
    memoryRejected = { "Rejected by core validation ($it)" },
    memoryRaw = "Source",
    memoryNoPage = "Open a page to see the Profile / Brief / Ledger it uses.",
    memoryEmptyBody = "(no body)",
    sideTab = {
        when (it) {
            SideTab.NOW -> "Now"
            SideTab.FILES -> "Files"
            SideTab.MEMORY -> "Memory"
            SideTab.GIT -> "Git"
            SideTab.PORTS -> "Ports"
            SideTab.HISTORY -> "History"
        }
    },
    sideTabPending = "This tab is empty for now.",
    lineLabel = { "line $it" },
    unknownFilesTitle = "Unregistered files",
    unknownFileAction = {
        when (it) {
            UnknownFileAction.Action.ARTIFACT -> "Artifact"
            UnknownFileAction.Action.KEEP -> "Keep"
            UnknownFileAction.Action.DELETE -> "Delete"
        }
    },
    decisionTitle = "Decision needed",
    decisionSent = "Answer sent. Waiting for the flow to resume.",
    yes = "Yes",
    no = "No",
    waitingReason = {
        when (it) {
            "no_runner" -> "No runner is available, so the flow stopped. Check runners in settings."
            else -> "The flow is waiting: $it"
        }
    },
    recentlyDeleted = "Recently deleted",
    trashEmpty = "Nothing was deleted recently",
    trashPage = "Page",
    trashBlock = { "Block $it" },
    restore = "Restore",
    searchTitle = "Search pages",
    searchPlaceholder = "Title, text, #tag",
    searchEmpty = "No matching pages",
    close = "Close"
)
