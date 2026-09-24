package madang.shared.main

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.MemoryApi
import madang.api.model.Issue
import madang.api.model.Memory
import madang.api.model.MemoryContent
import madang.api.model.MemoryFile
import madang.api.model.MemoryLayer
import madang.shared.core.CoreApiException
import madang.shared.core.bodyOrThrow

/**
 * 편집 중인 메모리 파일 하나.
 *
 * @property file core가 마지막으로 돌려준 파일.
 * @property issues 마지막 저장에서 core 검사기가 거부한 이유.
 * @property saved 마지막 저장이 성공했고 그 뒤로 고치지 않았다.
 */
data class MemoryDraft(
    val file: MemoryFile,
    val text: String = file.content,
    val issues: List<Issue> = emptyList(),
    val saving: Boolean = false,
    val saved: Boolean = false
) {
    val dirty: Boolean get() = text != file.content

    /** 줄 번호(1부터)별 문제. */
    val issuesByLine: Map<Int, List<Issue>>
        get() = issues.filter { it.line != null }.groupBy { checkNotNull(it.line) }

    /** 줄을 가리키지 않는 문제(토큰 상한 등). */
    val fileIssues: List<Issue> get() = issues.filter { it.line == null }
}

/**
 * 메모리 패널 상태. [page]가 null이면 닫혀 있다.
 *
 * @property drafts 층별 파일. 불러오기 전에는 비어 있다.
 * @property error 불러오기나 저장이 검사 외의 이유로 실패했을 때의 원인.
 */
data class MemoryState(
    val page: String? = null,
    val layer: MemoryLayer = MemoryLayer.STATE,
    val drafts: Map<MemoryLayer, MemoryDraft> = emptyMap(),
    val error: String? = null
) {
    val isOpen: Boolean get() = page != null

    val current: MemoryDraft? get() = drafts[layer]
}

/**
 * 메모리 패널. root·space·state 세 파일을 core에서 받아 고치고 저장한다.
 *
 * 저장은 core 검사기를 통과해야 한다. 거부되면(400) 오류를 줄 위치와 함께 [MemoryDraft.issues]에
 * 둔다. 다른 곳에서 파일이 바뀌면(`memory.updated`) 고치지 않은 층만 다시 받는다.
 */
class MemoryViewModel(private val api: MemoryApi, private val scope: CoroutineScope) {

    private val _state = MutableStateFlow(MemoryState())
    val state: StateFlow<MemoryState> = _state.asStateFlow()

    fun open(page: String) {
        if (_state.value.page == page) return
        _state.value = MemoryState(page = page, layer = _state.value.layer)
        reload(page)
    }

    fun close() {
        _state.value = MemoryState(layer = _state.value.layer)
    }

    fun select(layer: MemoryLayer) = _state.update { it.copy(layer = layer) }

    fun edit(text: String) = updateDraft(_state.value.layer) {
        it.copy(text = text, saved = false)
    }

    /** 고른 층을 저장한다. */
    fun save() {
        val state = _state.value
        val page = state.page ?: return
        val layer = state.layer
        val draft = state.current?.takeIf { it.dirty && !it.saving } ?: return
        updateDraft(layer) { it.copy(saving = true) }
        scope.launch {
            try {
                val saved = api.saveMemory(page, layer, MemoryContent(draft.text)).bodyOrThrow()
                val text = currentText(layer, draft.text, saved)
                replaceIf(page) { drafts ->
                    drafts +
                        (layer to MemoryDraft(saved, text = text, saved = text == saved.content))
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: CoreApiException) {
                rejected(page, layer, e)
            } catch (e: Exception) {
                failed(page, layer, e.message ?: e::class.simpleName)
            }
        }
    }

    /** `memory.updated`. 열린 페이지의 state, 또는 모든 페이지가 함께 쓰는 root·space면 다시 받는다. */
    fun onUpdated(page: String?, layer: MemoryLayer) {
        val open = _state.value.page ?: return
        if (layer == MemoryLayer.STATE && page != open) return
        reload(open)
    }

    private fun reload(page: String) {
        scope.launch {
            try {
                val memory = api.getMemory(page).bodyOrThrow()
                replaceIf(page) { drafts -> merge(drafts, memory) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update {
                    if (it.page == page) it.copy(error = e.message ?: e::class.simpleName) else it
                }
            }
        }
    }

    /** 새로 받은 파일로 바꾸되 고치던 층은 사용자의 문장을 둔다. */
    private fun merge(drafts: Map<MemoryLayer, MemoryDraft>, memory: Memory) =
        listOf(memory.root, memory.space, memory.state).associate { file ->
            val old = drafts[file.layer]
            file.layer to if (old != null && old.dirty) old.copy(file = file) else MemoryDraft(file)
        }

    /** 저장하는 사이 더 고쳤으면 그 문장을 둔다. */
    private fun currentText(layer: MemoryLayer, sent: String, saved: MemoryFile): String {
        val now = _state.value.drafts[layer]?.text ?: return saved.content
        return if (now == sent) saved.content else now
    }

    private fun rejected(page: String, layer: MemoryLayer, e: CoreApiException) {
        if (e.status != HTTP_BAD_REQUEST) return failed(page, layer, e.message)
        val issues = e.issues.ifEmpty {
            listOf(Issue(code = e.error?.error ?: "invalid", message = e.error?.message ?: ""))
        }
        replaceIf(page) { drafts ->
            val draft = drafts[layer] ?: return@replaceIf drafts
            drafts + (layer to draft.copy(saving = false, saved = false, issues = issues))
        }
    }

    private fun failed(page: String, layer: MemoryLayer, message: String?) {
        replaceIf(page) { drafts ->
            val draft = drafts[layer] ?: return@replaceIf drafts
            drafts + (layer to draft.copy(saving = false))
        }
        _state.update { if (it.page == page) it.copy(error = message) else it }
    }

    private fun updateDraft(layer: MemoryLayer, change: (MemoryDraft) -> MemoryDraft) =
        _state.update { state ->
            val draft = state.drafts[layer] ?: return@update state
            state.copy(drafts = state.drafts + (layer to change(draft)), error = null)
        }

    /** 그사이 패널이 다른 페이지로 바뀌었으면 결과를 버린다. */
    private fun replaceIf(
        page: String,
        change: (Map<MemoryLayer, MemoryDraft>) -> Map<MemoryLayer, MemoryDraft>
    ) = _state.update { if (it.page == page) it.copy(drafts = change(it.drafts)) else it }

    private companion object {
        const val HTTP_BAD_REQUEST = 400
    }
}
