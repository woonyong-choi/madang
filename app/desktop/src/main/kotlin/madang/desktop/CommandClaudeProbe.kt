package madang.desktop

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import madang.shared.onboarding.ClaudeProbe
import madang.shared.onboarding.ClaudeStatus

/**
 * `<bin> auth status`를 실행해 설치·로그인 여부를 본다.
 *
 * 출력 JSON에서 `loggedIn`과 `authMethod`만 읽는다. 계정 정보 등 다른 값은 버리고, 인증 파일은
 * 읽지 않으며 로그인도 시도하지 않는다. 명령을 실행하지 못하면 설치되지 않은 것으로 본다.
 */
class CommandClaudeProbe : ClaudeProbe {

    override suspend fun check(bin: String): ClaudeStatus = withContext(Dispatchers.IO) {
        val process = try {
            ProcessBuilder(bin, "auth", "status").redirectErrorStream(true).start()
        } catch (e: IOException) {
            return@withContext ClaudeStatus(installed = false, loggedIn = false)
        }
        if (!process.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            process.destroy()
            return@withContext ClaudeStatus(installed = true, loggedIn = false, error = "timeout")
        }
        parseAuthStatus(process.inputStream.bufferedReader().readText())
    }

    private companion object {
        const val TIMEOUT_SECONDS = 10L
    }
}

/** `claude auth status` 출력에서 로그인 여부와 방식만 꺼낸다. JSON이 아니면 로그인 안 됨. */
fun parseAuthStatus(output: String): ClaudeStatus {
    val status = runCatching { Json.parseToJsonElement(output).jsonObject }.getOrNull()
        ?: return ClaudeStatus(installed = true, loggedIn = false)
    val loggedIn = status["loggedIn"]?.jsonPrimitive?.booleanOrNull == true
    val method = status["authMethod"]?.jsonPrimitive?.contentOrNull
    return ClaudeStatus(
        installed = true,
        loggedIn = loggedIn,
        authMethod = method.takeIf {
            loggedIn
        }
    )
}
