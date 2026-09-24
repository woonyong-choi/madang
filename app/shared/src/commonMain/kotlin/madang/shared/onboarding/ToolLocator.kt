package madang.shared.onboarding

/**
 * 에이전트 도구(`claude`, `codex`) 실행 파일의 절대 경로를 확인한다.
 *
 * Finder 등으로 연 앱은 셸 PATH를 받지 않는다. 그래서 사용자의 로그인 셸이 실제로 찾은 경로나
 * 사용자가 직접 고른 경로만 쓰고, 흔한 설치 위치를 뒤지는 추측은 하지 않는다.
 */
interface ToolLocator {
    /** 로그인 셸에서 [tool]을 찾은 절대 경로. 못 찾으면 null. */
    suspend fun locate(tool: String): String?

    /** [path]가 실행할 수 있는 파일의 절대 경로인지 본다. 사용자가 고른 경로를 확인할 때 쓴다. */
    suspend fun isExecutable(path: String): Boolean
}

/** 도구를 찾을 수 없는 플랫폼. 아무것도 찾지 못하고 어떤 경로도 받지 않는다. */
object NoToolLocator : ToolLocator {
    override suspend fun locate(tool: String): String? = null

    override suspend fun isExecutable(path: String): Boolean = false
}
