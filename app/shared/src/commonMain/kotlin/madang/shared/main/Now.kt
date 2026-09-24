package madang.shared.main

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.RunnersApi
import madang.api.client.RunsApi
import madang.api.model.RunInput
import madang.api.model.RunProgressEvent
import madang.api.model.RunStreamEvent
import madang.api.model.Usage
import madang.shared.core.bodyOrThrow

/** 진행 로그를 펼쳤을 때 보이는 줄 수. */
const val NOW_LOG_LINES = 30

/** 지금 탭에서 고른 run 하나(페이지와 run 번호). */
data class RunKey(val page: String, val n: Int)

/**
 * 지금 탭 상태.
 *
 * @property usage 구독 도구의 사용량(`GET /usage`). 받은 적이 없으면 null.
 * @property log 진행 로그를 펼친 run과 그 마지막 [NOW_LOG_LINES]개 이벤트.
 * @property input 입력 구성을 보는 run과 그 구성. core가 입력 구성을 남기지 않았으면 값이 null.
 */
data class NowState(
    val usage: Load<Usage>? = null,
    val log: Pair<RunKey, Load<List<RunStreamEvent>>>? = null,
    val input: Pair<RunKey, Load<RunInput?>>? = null
)

/**
 * 지금 탭. 줄 목록은 메인 상태에서 만들고([nowItems]), 이 ViewModel은 줄마다 따로 받는 것을 맡는다:
 * 사용량, 펼친 진행 로그(받은 뒤로는 `run.progress`를 이어 붙인다), 누른 run의 입력 구성.
 */
class NowViewModel(
    private val runs: RunsApi,
    private val runners: RunnersApi,
    private val scope: CoroutineScope
) {
    private val _state = MutableStateFlow(NowState())
    val state: StateFlow<NowState> = _state.asStateFlow()

    /** 사용량을 다시 받는다. 받는 동안 앞의 값을 그대로 보인다. */
    fun refreshUsage() {
        _state.update { it.copy(usage = it.usage.takeIf { u -> u is Load.Ready } ?: Load.Loading) }
        scope.launch {
            val loaded = loadOf { runners.getUsage().bodyOrThrow() }
            _state.update { it.copy(usage = loaded) }
        }
    }

    /** [item]의 진행 로그를 펼치거나 접는다. 펼치면 그 run의 이벤트 로그를 받는다. */
    fun toggleLog(item: NowItem) {
        val key = item.key() ?: return
        if (_state.value.log?.first == key) {
            _state.update { it.copy(log = null) }
            return
        }
        _state.update { it.copy(log = key to Load.Loading) }
        scope.launch {
            val loaded = loadOf {
                runs.listRunEvents(key.page, key.n).bodyOrThrow().takeLast(NOW_LOG_LINES)
            }
            _state.update { if (it.log?.first == key) it.copy(log = key to loaded) else it }
        }
    }

    /**
     * [item]을 눌렀다: 마지막 호출의 입력 구성을 보인다. 진행 중이고 `run.assembled`를 받았으면 그
     * 구성을, 아니면 run 기록(`GET /pages/{p}/runs/{n}`)의 구성을 쓴다. 같은 줄을 다시 누르면 닫는다.
     */
    fun showInput(item: NowItem) {
        val key = item.key() ?: return
        if (_state.value.input?.first == key) {
            _state.update { it.copy(input = null) }
            return
        }
        val assembled = item.active?.input
        if (assembled != null) {
            _state.update { it.copy(input = key to Load.Ready(assembled)) }
            return
        }
        _state.update { it.copy(input = key to Load.Loading) }
        scope.launch {
            val loaded = loadOf { runs.getRun(key.page, key.n).bodyOrThrow().input }
            _state.update { if (it.input?.first == key) it.copy(input = key to loaded) else it }
        }
    }

    /** 펼친 run의 `run.progress`를 로그 끝에 붙인다. 앞은 [NOW_LOG_LINES]개만 남긴다. */
    fun onProgress(event: RunProgressEvent) = _state.update { state ->
        val (key, log) = state.log ?: return@update state
        if (key != RunKey(event.page, event.run) || log !is Load.Ready) return@update state
        state.copy(log = key to Load.Ready((log.value + event.data).takeLast(NOW_LOG_LINES)))
    }

    private fun NowItem.key(): RunKey? = n?.let { RunKey(page, it) }
}
