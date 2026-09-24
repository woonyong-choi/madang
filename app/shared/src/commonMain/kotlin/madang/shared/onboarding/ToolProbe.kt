package madang.shared.onboarding

/** 에이전트 CLI 하나의 설치 상태. */
data class ToolStatus(val path: String?, val version: String?, val error: String? = null) {
    val installed: Boolean get() = path != null
}

/** `which <tool>`과 `<tool> --version`으로 설치 여부를 본다. 로그인은 시도하지 않는다. */
fun interface ToolProbe {
    suspend fun probe(tool: String): ToolStatus
}
