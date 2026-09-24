package madang.shared.core

import io.ktor.client.HttpClient
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import madang.api.model.BlockAddedEvent
import madang.api.model.BlockDeletedEvent
import madang.api.model.BlockUpdatedEvent
import madang.api.model.EventEnvelope
import madang.api.model.EventType
import madang.api.model.FlowWaitingEvent
import madang.api.model.MemoryUpdatedEvent
import madang.api.model.PageCreatedEvent
import madang.api.model.PageDeletedEvent
import madang.api.model.PageUnknownFilesEvent
import madang.api.model.PageUpdatedEvent
import madang.api.model.ProjectCreatedEvent
import madang.api.model.ProjectDeletedEvent
import madang.api.model.ProjectUpdatedEvent
import madang.api.model.RunAssembledEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFallbackEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunProgressEvent
import madang.api.model.RunStartedEvent
import madang.api.model.RunnerAvailabilityEvent

/**
 * core 이벤트 하나.
 *
 * [payload]는 [EventEnvelope.type]에 맞는 생성 모델이다(`RunProgressEvent` 등).
 */
data class CoreEvent(val envelope: EventEnvelope, val payload: Any)

/** [EventStream]이 내보내는 항목. */
sealed interface EventStreamItem {
    /**
     * 연결이 열렸다. 받은 쪽은 프로젝트·페이지·열린 페이지를 전부 다시 가져온다.
     * [reconnected]는 끊긴 뒤 다시 붙었을 때 참이다.
     */
    data class Resync(val reconnected: Boolean) : EventStreamItem

    /** 연결이 끊겼다. [retryIn] 뒤에 다시 붙는다. */
    data class Disconnected(val cause: String?, val retryIn: Duration) : EventStreamItem

    data class Received(val event: CoreEvent) : EventStreamItem
}

/** 이벤트 연결 하나를 연다. 연결이 닫히면 돌아오고, 실패하면 예외를 던진다. */
fun interface EventTransport {
    suspend fun open(onOpen: suspend () -> Unit, onFrame: suspend (String) -> Unit)
}

/** Ktor WebSocket으로 `WS /events`에 붙는다. */
class WebSocketEventTransport(private val http: HttpClient, baseUrl: String) : EventTransport {

    private val eventsUrl = baseUrl.trimEnd('/').replaceFirst("http", "ws") + "/events"

    override suspend fun open(onOpen: suspend () -> Unit, onFrame: suspend (String) -> Unit) {
        http.webSocket(eventsUrl) {
            onOpen()
            for (frame in incoming) {
                if (frame is Frame.Text) onFrame(frame.readText())
            }
        }
    }
}

/**
 * `WS /events`를 [Flow]로 바꾼다.
 *
 * 연결이 끊기면 [retryDelay]만큼 기다렸다가 다시 붙고, 붙을 때마다
 * [EventStreamItem.Resync]를 내보낸다. 모르는 이벤트와 깨진 프레임은 건너뛴다.
 */
class EventStream(
    private val transport: EventTransport,
    private val retryDelay: (attempt: Int) -> Duration = ::backoff
) {

    fun items(): Flow<EventStreamItem> = channelFlow {
        var opened = false
        var failures = 0
        while (true) {
            val cause = try {
                transport.open(
                    onOpen = {
                        send(EventStreamItem.Resync(reconnected = opened))
                        opened = true
                        failures = 0
                    },
                    onFrame = { text ->
                        decodeEvent(text)?.let { send(EventStreamItem.Received(it)) }
                    }
                )
                null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                e.message ?: e::class.simpleName
            }
            failures++
            val wait = retryDelay(failures)
            send(EventStreamItem.Disconnected(cause, wait))
            delay(wait)
        }
    }

    companion object {
        /** 1초에서 시작해 두 배씩, 최대 15초. */
        fun backoff(attempt: Int): Duration =
            (1 shl (attempt - 1).coerceIn(0, 4)).seconds.coerceAtMost(15.seconds)
    }
}

/** 봉투로 `type`을 먼저 읽고 구체 이벤트로 다시 해석한다. 해석할 수 없으면 null. */
fun decodeEvent(text: String): CoreEvent? = try {
    val envelope = CoreClient.CoreJson.decodeFromString(EventEnvelope.serializer(), text)
    val payload = CoreClient.CoreJson.decodeFromString(serializerFor(envelope.type), text)
    CoreEvent(envelope, payload)
} catch (e: SerializationException) {
    null
} catch (e: IllegalArgumentException) {
    null
}

private fun serializerFor(type: EventType): KSerializer<out Any> = when (type) {
    EventType.PROJECT_PERIOD_CREATED -> ProjectCreatedEvent.serializer()
    EventType.PROJECT_PERIOD_UPDATED -> ProjectUpdatedEvent.serializer()
    EventType.PROJECT_PERIOD_DELETED -> ProjectDeletedEvent.serializer()
    EventType.PAGE_PERIOD_CREATED -> PageCreatedEvent.serializer()
    EventType.PAGE_PERIOD_UPDATED -> PageUpdatedEvent.serializer()
    EventType.PAGE_PERIOD_DELETED -> PageDeletedEvent.serializer()
    EventType.BLOCK_PERIOD_ADDED -> BlockAddedEvent.serializer()
    EventType.BLOCK_PERIOD_UPDATED -> BlockUpdatedEvent.serializer()
    EventType.BLOCK_PERIOD_DELETED -> BlockDeletedEvent.serializer()
    EventType.RUN_PERIOD_STARTED -> RunStartedEvent.serializer()
    EventType.RUN_PERIOD_ASSEMBLED -> RunAssembledEvent.serializer()
    EventType.RUN_PERIOD_PROGRESS -> RunProgressEvent.serializer()
    EventType.RUN_PERIOD_FINISHED -> RunFinishedEvent.serializer()
    EventType.RUN_PERIOD_FAILED -> RunFailedEvent.serializer()
    EventType.RUN_PERIOD_FALLBACK -> RunFallbackEvent.serializer()
    EventType.PAGE_PERIOD_UNKNOWN_FILES -> PageUnknownFilesEvent.serializer()
    EventType.FLOW_PERIOD_WAITING -> FlowWaitingEvent.serializer()
    EventType.MEMORY_PERIOD_UPDATED -> MemoryUpdatedEvent.serializer()
    EventType.RUNNER_PERIOD_AVAILABILITY -> RunnerAvailabilityEvent.serializer()
}
