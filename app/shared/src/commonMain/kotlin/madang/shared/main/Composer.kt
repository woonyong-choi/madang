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
 * @property target 보낼 곳(활성 탭). 열린 페이지가 없으면 null.
 * @property preview 지금 문장으로 다음 호출을 하면 읽을 입력의 추정치.
 */
data class ComposerState(
    val target: SendTarget? = null,
    val text: String = "",
    val preview: InputPreview? = null
) {
    val page: String? get() = target?.page

    val canSend: Boolean get() = target != null && text.isNotBlank()
}

/** 입력창에서 꺼낸 보낼 문장과 그 대상. */
data class Outgoing(val target: SendTarget, val text: String)

/** 입력창에서 누른 키가 할 일. */
enum class ComposerKey { SEND, NEWLINE }

/**
 * 입력창 키 규칙. Enter와 Cmd/Ctrl+Enter는 보내기, Shift+Enter는 줄바꿈이다. 입력창이 처리하지
 * 않는 키면 null.
 *
 * 입력기가 글자를 조합하는 중([composing], 한글 등)이면 Enter는 조합을 확정하는 키이므로 입력기에
 * 넘긴다.
 */
fun composerKey(enter: Boolean, shift: Boolean, composing: Boolean = false): ComposerKey? = when {
    composing || !enter -> null
    shift -> ComposerKey.NEWLINE
    else -> ComposerKey.SEND
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

    /**
     * 보낼 곳을 바꾼다. 다른 페이지면 쓰던 문장과 추정치를 비우고, 같은 페이지의 다른 탭이면
     * 문장은 두고 추정치만 새로 받는다.
     */
    fun setTarget(target: SendTarget?) {
        val current = _state.value
        if (current.target == target) return
        _state.value = if (current.page == target?.page) {
            current.copy(target = target, preview = null)
        } else {
            ComposerState(target = target)
        }
        schedulePreview()
    }

    fun setText(text: String) {
        if (_state.value.text == text) return
        _state.update { it.copy(text = text) }
        schedulePreview()
    }

    /** 보낼 문장과 대상을 꺼내고 입력창을 비운다. 보낼 것이 없으면 null. */
    fun take(): Outgoing? {
        val current = _state.value
        val target = current.target ?: return null
        if (!current.canSend) return null
        setText("")
        return Outgoing(target, current.text.trim())
    }

    /** 보내기에 실패한 문장을 되돌린다. 그사이 새로 쓴 문장이 있으면 두고 버리지 않는다. */
    fun restore(page: String, text: String) {
        val current = _state.value
        if (current.page == page && current.text.isEmpty()) setText(text)
    }

    private fun schedulePreview() {
        previewJob?.cancel()
        val snapshot = _state.value
        val target = snapshot.target ?: return
        previewJob = scope.launch {
            delay(debounce)
            val preview = fetchPreview(target, snapshot.text) ?: return@launch
            _state.update {
                if (it.target == target && it.text == snapshot.text) {
                    it.copy(preview = preview)
                } else {
                    it
                }
            }
        }
    }

    /** 추정치는 보조 정보이므로 실패하면 조용히 이전 값을 둔다. */
    private suspend fun fetchPreview(target: SendTarget, text: String): InputPreview? = try {
        messages.previewInput(target.page, target = target.block, text = text.ifBlank { null })
            .bodyOrThrow()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    companion object {
        val PREVIEW_DEBOUNCE = 300.milliseconds
    }
}
