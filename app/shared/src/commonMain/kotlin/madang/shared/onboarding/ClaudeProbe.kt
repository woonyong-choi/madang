package madang.shared.onboarding

/**
 * claude CLI의 설치·로그인 상태.
 *
 * @property authMethod 로그인 방식(`claude.ai` 등). 로그인하지 않았으면 null.
 * @property error 명령을 실행하지 못한 이유.
 */
data class ClaudeStatus(
    val installed: Boolean,
    val loggedIn: Boolean,
    val authMethod: String? = null,
    val error: String? = null
)

/** `claude auth status` 결과로 설치·로그인 여부를 본다. 인증 파일은 읽지 않고 로그인도 하지 않는다. */
fun interface ClaudeProbe {
    suspend fun check(): ClaudeStatus
}
