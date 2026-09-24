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

/** 메모리 탭이 층을 보여 주는 순서. 언제나 이 순서다. */
val MEMORY_ORDER = listOf(MemoryLayer.PROFILE, MemoryLayer.BRIEF, MemoryLayer.LEDGER)

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
 * 검사 문제를 폼의 자리로 나눈 것.
 *
 * @property byField 머리부 키 줄(1부터)별 문제.
 * @property body 본문 줄을 가리키는 문제.
 * @property loose 줄이 없거나 머리부 구분선처럼 키·본문 밖을 가리키는 문제.
 */
data class PlacedIssues(
    val byField: Map<Int, List<Issue>>,
    val body: List<Issue>,
    val loose: List<Issue>
)

/** [issues]를 [parts]의 머리부 키·본문·그 밖으로 나눈다. */
fun placeIssues(parts: MemoryParts, issues: List<Issue>): PlacedIssues {
    val byField = mutableMapOf<Int, List<Issue>>()
    val body = mutableListOf<Issue>()
    val loose = mutableListOf<Issue>()
    for (issue in issues) {
        val line = issue.line
        val field = line?.let { l -> parts.fields.firstOrNull { l in it } }
        when {
            field != null -> byField[field.line] = byField[field.line].orEmpty() + issue
            line != null && line >= parts.bodyLine -> body += issue
            else -> loose += issue
        }
    }
    return PlacedIssues(byField, body, loose)
}

/**
 * 메모리 탭 상태. [page]가 null이면 닫혀 있다.
 *
 * @property drafts 층별 파일. 불러오기 전에는 비어 있다.
 * @property raw 원문 편집기로 보는 층. 나머지는 머리부 폼과 본문으로 보인다.
 * @property error 불러오기나 저장이 검사 외의 이유로 실패했을 때의 원인.
 */
data class MemoryState(
    val page: String? = null,
    val drafts: Map<MemoryLayer, MemoryDraft> = emptyMap(),
    val raw: Set<MemoryLayer> = emptySet(),
    val error: String? = null
) {
    val isOpen: Boolean get() = page != null

    /** [MEMORY_ORDER] 순서의 파일. */
    val ordered: List<MemoryDraft> get() = MEMORY_ORDER.mapNotNull(drafts::get)
}

/**
 * 메모리 탭. Profile·Brief·Ledger 세 파일을 core에서 받아 고치고 층마다 저장한다.
 *
 * 저장은 core 검사기를 통과해야 한다. 거부되면(400) 오류를 줄 위치와 함께 [MemoryDraft.issues]에
 * 둔다. 다른 곳에서 파일이 바뀌면(`memory.updated`) 고치지 않은 층만 다시 받는다.
 */
class MemoryViewModel(private val api: MemoryApi, private val scope: CoroutineScope) {

    private val _state = MutableStateFlow(MemoryState())
    val state: StateFlow<MemoryState> = _state.asStateFlow()

    fun open(page: String) {
        if (_state.value.page == page) return
        _state.value = MemoryState(page = page, raw = _state.value.raw)
        reload(page)
    }

    fun close() {
        _state.value = MemoryState(raw = _state.value.raw)
    }

    /** [layer]를 원문 편집기와 머리부 폼·본문 사이에서 바꾼다. */
    fun toggleRaw(layer: MemoryLayer) = _state.update {
        it.copy(raw = if (layer in it.raw) it.raw - layer else it.raw + layer)
    }

    fun edit(layer: MemoryLayer, text: String) = updateDraft(layer) {
        it.copy(text = text, saved = false)
    }

    /** 머리부 폼에서 [key]의 값을 고친다. 다른 줄은 그대로 둔다. */
    fun editField(layer: MemoryLayer, key: String, value: String) {
        val draft = _state.value.drafts[layer] ?: return
        edit(layer, withHeaderField(draft.text, key, value))
    }

    /** [layer]를 저장한다. */
    fun save(layer: MemoryLayer) {
        val page = _state.value.page ?: return
        val draft = _state.value.drafts[layer]?.takeIf { it.dirty && !it.saving } ?: return
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

    /** `memory.updated`. 열린 페이지의 Ledger, 또는 여러 페이지가 함께 쓰는 Profile·Brief면 다시 받는다. */
    fun onUpdated(page: String?, layer: MemoryLayer) {
        val open = _state.value.page ?: return
        if (layer == MemoryLayer.LEDGER && page != open) return
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
        listOf(memory.profile, memory.brief, memory.ledger).associate { file ->
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

    /** 그사이 탭이 다른 페이지로 바뀌었으면 결과를 버린다. */
    private fun replaceIf(
        page: String,
        change: (Map<MemoryLayer, MemoryDraft>) -> Map<MemoryLayer, MemoryDraft>
    ) = _state.update { if (it.page == page) it.copy(drafts = change(it.drafts)) else it }

    private companion object {
        const val HTTP_BAD_REQUEST = 400
    }
}
