package madang.shared.main

import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.MessagesApi
import madang.api.model.InputPreview
import madang.shared.core.bodyOrThrow

/**
 * 입력창 상태.
 *
 * @property page 보낼 대상 페이지. 열린 페이지가 없으면 null.
 * @property preview 지금 문장으로 다음 호출을 하면 읽을 입력의 추정치.
 */
data class ComposerState(
    val page: String? = null,
    val text: String = "",
    val preview: InputPreview? = null
) {
    val suggestions: List<String> get() = prefixSuggestions(text)

    val canSend: Boolean get() = page != null && text.isNotBlank()
}

/** 종류를 강제하는 접두어. routes.yaml의 기본 종류와 같다. */
val KIND_PREFIXES = listOf("design", "build", "small", "review", "explore")

/**
 * 접두어 자동완성 후보(`design:` 등).
 *
 * 공백 없이 쓰는 첫 단어가 종류 이름의 앞부분이면 후보를 낸다. 이미 `:`를 썼거나 종류 이름을
 * 다 썼으면 후보가 없다.
 */
fun prefixSuggestions(text: String, kinds: List<String> = KIND_PREFIXES): List<String> {
    if (text.isEmpty() || text.any { it.isWhitespace() || it == ':' }) return emptyList()
    val typed = text.lowercase()
    return kinds.filter { it.startsWith(typed) && it != typed }.map { "$it:" }
}

/** 입력창에서 누른 키가 할 일. */
enum class ComposerKey { SEND, NEWLINE, COMPLETE }

/**
 * 입력창 키 규칙. Enter와 Cmd/Ctrl+Enter는 보내기, Shift+Enter는 줄바꿈, 후보가 있을 때
 * Tab은 자동완성이다. 입력창이 처리하지 않는 키면 null.
 */
fun composerKey(
    enter: Boolean,
    tab: Boolean,
    shift: Boolean,
    hasSuggestions: Boolean
): ComposerKey? = when {
    enter && shift -> ComposerKey.NEWLINE
    enter -> ComposerKey.SEND
    tab && hasSuggestions && !shift -> ComposerKey.COMPLETE
    else -> null
}

/**
 * 입력창. 문장이 바뀔 때마다 [debounce]만큼 기다렸다가 `GET /preview-input`으로 다음 호출의
 * 입력 토큰을 추정한다. 그사이 문장이 또 바뀌면 앞 요청은 버린다.
 */
class ComposerViewModel(
    private val messages: MessagesApi,
    private val scope: CoroutineScope,
    private val debounce: Duration = PREVIEW_DEBOUNCE
) {
    private val _state = MutableStateFlow(ComposerState())
    val state: StateFlow<ComposerState> = _state.asStateFlow()

    private var previewJob: Job? = null

    /** 대상 페이지를 바꾼다. 다른 페이지면 쓰던 문장과 추정치를 비운다. */
    fun setPage(page: String?) {
        if (_state.value.page == page) return
        _state.value = ComposerState(page = page)
        schedulePreview()
    }

    fun setText(text: String) {
        if (_state.value.text == text) return
        _state.update { it.copy(text = text) }
        schedulePreview()
    }

    /** 첫 단어를 고른 접두어로 바꾼다. */
    fun complete(prefix: String) = setText("$prefix ")

    /** 보낼 문장을 꺼내고 입력창을 비운다. 보낼 것이 없으면 null. */
    fun take(): String? {
        val current = _state.value
        if (!current.canSend) return null
        setText("")
        return current.text.trim()
    }

    /** 보내기에 실패한 문장을 되돌린다. 그사이 새로 쓴 문장이 있으면 두고 버리지 않는다. */
    fun restore(page: String, text: String) {
        val current = _state.value
        if (current.page == page && current.text.isEmpty()) setText(text)
    }

    private fun schedulePreview() {
        previewJob?.cancel()
        val snapshot = _state.value
        val page = snapshot.page ?: return
        previewJob = scope.launch {
            delay(debounce)
            val preview = fetchPreview(page, snapshot.text) ?: return@launch
            _state.update {
                if (it.page == page && it.text == snapshot.text) it.copy(preview = preview) else it
            }
        }
    }

    /** 추정치는 보조 정보이므로 실패하면 조용히 이전 값을 둔다. */
    private suspend fun fetchPreview(page: String, text: String): InputPreview? = try {
        messages.previewInput(page, text = text.ifBlank { null }).bodyOrThrow()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    companion object {
        val PREVIEW_DEBOUNCE = 300.milliseconds
    }
}
