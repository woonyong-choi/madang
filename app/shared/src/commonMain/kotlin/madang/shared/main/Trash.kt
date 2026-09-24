package madang.shared.main

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.TrashApi
import madang.api.model.TrashEntry
import madang.shared.core.bodyOrThrow

/**
 * 최근 삭제 목록.
 *
 * @property entries 최신순 삭제 내역. 아직 받지 않았으면 null.
 * @property restoring 복구 요청 중인 휴지통 항목 id.
 */
data class TrashState(
    val entries: List<TrashEntry>? = null,
    val restoring: String? = null,
    val error: String? = null
)

/**
 * 최근 삭제(`GET /trash`)와 복구. 항목은 각 프로젝트의 `.madang/trash/`에 있다. 복구하면
 * 목록을 다시 받고 [onRestored]로 알린다.
 */
class TrashViewModel(
    private val api: TrashApi,
    private val scope: CoroutineScope,
    private val onRestored: () -> Unit
) {
    private val _state = MutableStateFlow(TrashState())
    val state: StateFlow<TrashState> = _state.asStateFlow()

    /** 목록을 새로 받는다. 대화상자를 열 때 부른다. */
    fun load() {
        _state.value = TrashState()
        request { _state.update { it.copy(entries = api.listTrash().bodyOrThrow()) } }
    }

    fun restore(id: String) {
        if (_state.value.restoring != null) return
        _state.update { it.copy(restoring = id, error = null) }
        request {
            api.restoreTrash(id).bodyOrThrow()
            val entries = api.listTrash().bodyOrThrow()
            _state.update { it.copy(entries = entries, restoring = null) }
            onRestored()
        }
    }

    private fun request(block: suspend () -> Unit) {
        scope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update {
                    it.copy(restoring = null, error = e.message ?: e::class.simpleName)
                }
            }
        }
    }
}
