package madang.shared.main

import kotlin.time.Duration
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.SpacesApi
import madang.api.model.Space
import madang.shared.core.CoreClient
import madang.shared.core.EventStream
import madang.shared.core.EventStreamItem
import madang.shared.core.bodyOrThrow

/** 이벤트 연결 상태. */
sealed interface EventLink {
    data object Connecting : EventLink

    data object Live : EventLink

    data class Retrying(val cause: String?, val retryIn: Duration) : EventLink
}

/** 최근 이벤트 한 줄. */
data class EventLine(val type: String, val ts: String, val page: String?)

data class MainState(
    val baseUrl: String,
    val link: EventLink = EventLink.Connecting,
    val spaces: List<Space> = emptyList(),
    val loadError: String? = null,
    val resyncs: Int = 0,
    val recentEvents: List<EventLine> = emptyList()
)

/**
 * 메인 화면의 연결 부분. 이벤트 스트림을 구독하고, 연결이 열릴 때마다 전체를 다시
 * 가져온다. 이벤트가 오면 공간 목록을 갱신한다.
 */
class MainViewModel(
    private val core: CoreClient,
    events: EventStream,
    private val scope: CoroutineScope
) {
    private val _state = MutableStateFlow(MainState(baseUrl = core.baseUrl))
    val state: StateFlow<MainState> = _state.asStateFlow()

    private val spacesApi = core.api(::SpacesApi)

    init {
        scope.launch { events.items().collect(::onItem) }
    }

    private fun onItem(item: EventStreamItem) {
        when (item) {
            is EventStreamItem.Resync -> {
                _state.update { it.copy(link = EventLink.Live, resyncs = it.resyncs + 1) }
                reload()
            }

            is EventStreamItem.Disconnected ->
                _state.update { it.copy(link = EventLink.Retrying(item.cause, item.retryIn)) }

            is EventStreamItem.Received -> {
                val envelope = item.event.envelope
                val line = EventLine(envelope.type.value, envelope.ts, envelope.page)
                _state.update {
                    it.copy(recentEvents = (listOf(line) + it.recentEvents).take(RECENT_LIMIT))
                }
                if (envelope.type.value.startsWith("space.")) reload()
            }
        }
    }

    private fun reload() {
        scope.launch {
            try {
                val spaces = spacesApi.listSpaces().bodyOrThrow()
                _state.update { it.copy(spaces = spaces, loadError = null) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(loadError = e.message ?: "error") }
            }
        }
    }

    private companion object {
        const val RECENT_LIMIT = 20
    }
}
