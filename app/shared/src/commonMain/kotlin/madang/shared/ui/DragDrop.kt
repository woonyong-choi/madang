package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import madang.api.model.PageCard

/** 페이지 카드를 놓을 수 있는 곳. */
sealed interface DropTarget {
    data class ToProject(val id: String) : DropTarget

    data class ToTag(val path: String) : DropTarget
}

/** [point]를 담은 대상. 겹치면 나중에 등록된 것. */
fun hitTarget(targets: Map<DropTarget, Rect>, point: Offset): DropTarget? =
    targets.entries.lastOrNull { it.value.contains(point) }?.key

/**
 * 카드 끌어다 놓기. 좌표는 모두 창 기준이다.
 *
 * 카드는 [dragSource], 프로젝트·태그 줄은 [dropTarget]을 단다. 놓으면 [onDrop]이 불린다.
 */
class DragDropState(private val onDrop: (PageCard, DropTarget) -> Unit) {
    var dragging by mutableStateOf<PageCard?>(null)
        private set
    var pointer by mutableStateOf(Offset.Zero)
        private set
    var hovered by mutableStateOf<DropTarget?>(null)
        private set

    private val targets = mutableMapOf<DropTarget, Rect>()

    fun register(target: DropTarget, bounds: Rect) {
        targets[target] = bounds
    }

    fun unregister(target: DropTarget) {
        targets -= target
    }

    fun start(card: PageCard, at: Offset) {
        dragging = card
        pointer = at
        hovered = null
    }

    fun move(delta: Offset) {
        pointer += delta
        hovered = hitTarget(targets, pointer)
    }

    fun end() {
        val card = dragging
        val target = hovered
        cancel()
        if (card != null && target != null) onDrop(card, target)
    }

    fun cancel() {
        dragging = null
        hovered = null
    }
}

val LocalDragDrop = staticCompositionLocalOf<DragDropState?> { null }

/** 카드를 끌 수 있게 한다. 짧은 클릭은 그대로 클릭이다. */
fun Modifier.dragSource(card: PageCard): Modifier = composed {
    val drag = LocalDragDrop.current ?: return@composed this
    var coordinates by remember { mutableStateOf<LayoutCoordinates?>(null) }
    onGloballyPositioned { coordinates = it }
        .pointerInput(card.id) {
            detectDragGestures(
                onDragStart = { offset ->
                    val origin = coordinates?.positionInWindow() ?: Offset.Zero
                    drag.start(card, origin + offset)
                },
                onDrag = { change, amount ->
                    change.consume()
                    drag.move(amount)
                },
                onDragEnd = drag::end,
                onDragCancel = drag::cancel
            )
        }
}

/** 이 요소를 놓을 곳으로 등록한다. */
fun Modifier.dropTarget(target: DropTarget): Modifier = composed {
    val drag = LocalDragDrop.current ?: return@composed this
    DisposableEffect(target) { onDispose { drag.unregister(target) } }
    onGloballyPositioned { drag.register(target, it.boundsInWindow()) }
}

/** 끄는 동안 포인터 옆에 뜨는 카드 제목과 놓을 곳 안내. [origin]은 이 층의 창 기준 위치. */
@Composable
fun DragGhost(drag: DragDropState, origin: Offset, hint: (DropTarget) -> String) {
    val card = drag.dragging ?: return
    val at = drag.pointer - origin
    val label = drag.hovered?.let(hint) ?: card.title
    Box(
        modifier = Modifier
            .offset { IntOffset(at.x.toInt() + 12, at.y.toInt() + 12) }
            .background(MaterialTheme.colorScheme.inverseSurface, RoundedCornerShape(6.dp))
            .padding(horizontal = 10.dp, vertical = 6.dp)
    ) {
        Text(
            label,
            color = MaterialTheme.colorScheme.inverseOnSurface,
            style = MaterialTheme.typography.labelMedium
        )
    }
}
