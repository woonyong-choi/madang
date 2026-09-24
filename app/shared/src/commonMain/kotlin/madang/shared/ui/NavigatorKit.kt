package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.BugReport
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Code
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Lightbulb
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material.icons.outlined.Work
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.isSecondaryPressed
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.datetime.TimeZone
import madang.api.model.PageStatus
import madang.api.model.SpaceSort

/** 목록의 날짜 묶음과 카드 시각에 쓰는 지금과 시간대. 스크린샷 테스트는 고정한다. */
data class ListClock(val now: () -> Instant, val zone: TimeZone)

val LocalListClock = staticCompositionLocalOf {
    ListClock(now = { Clock.System.now() }, zone = TimeZone.currentSystemDefault())
}

/** 토큰 수. 1000 이상은 `29.1K`. */
fun formatTokens(count: Int): String {
    if (count < 1000) return "$count"
    val tenths = (count + 50) / 100
    return "${tenths / 10}.${tenths % 10}K"
}

/** 오른쪽 클릭(보조 버튼)을 받는다. [onClick]은 요소 안의 위치를 받는다. */
fun Modifier.onSecondaryClick(onClick: (Offset) -> Unit): Modifier = pointerInput(Unit) {
    awaitPointerEventScope {
        while (true) {
            val event = awaitPointerEvent()
            if (event.type == PointerEventType.Press && event.buttons.isSecondaryPressed) {
                event.changes.forEach { it.consume() }
                onClick(event.changes.first().position)
            }
        }
    }
}

/** 메뉴 항목 하나. */
data class MenuAction(val label: String, val onClick: () -> Unit)

/**
 * 오른쪽 클릭 메뉴를 가진 영역. [content]에 넘기는 Modifier를 대상 요소에 단다.
 */
@Composable
fun ContextMenuBox(actions: () -> List<MenuAction>, content: @Composable (Modifier) -> Unit) {
    var at by remember { mutableStateOf<Offset?>(null) }
    val density = LocalDensity.current
    Box {
        content(Modifier.onSecondaryClick { at = it })
        val point = at
        DropdownMenu(
            expanded = point != null,
            onDismissRequest = { at = null },
            offset = point?.let { with(density) { DpOffset(it.x.toDp(), 0.dp) } } ?: DpOffset.Zero
        ) {
            for (action in actions()) {
                DropdownMenuItem(
                    text = { Text(action.label) },
                    onClick = {
                        at = null
                        action.onClick()
                    }
                )
            }
        }
    }
}

/** 상태 칩. 카드와 본문 제목 옆에 쓴다. */
@Composable
fun StatusChip(status: PageStatus, modifier: Modifier = Modifier) {
    val color = statusColor(status)
    Box(
        modifier = modifier
            .background(color.copy(alpha = 0.14f), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 1.dp)
    ) {
        Text(
            LocalStrings.current.navigator.status(status),
            color = color,
            style = MaterialTheme.typography.labelSmall
        )
    }
}

fun statusColor(status: PageStatus): Color = when (status) {
    PageStatus.PLANNING -> Color(0xFF6B7280)
    PageStatus.DOING -> Color(0xFF2563EB)
    PageStatus.BLOCKED -> Color(0xFFDC2626)
    PageStatus.REVIEW -> Color(0xFFB45309)
    PageStatus.DONE -> Color(0xFF15803D)
}

/** 공간 아이콘 이름을 그림으로. 모르는 이름은 폴더. */
fun spaceIcon(name: String?, root: Boolean): ImageVector = when (name) {
    "briefcase", "work" -> Icons.Outlined.Work
    "calendar" -> Icons.Outlined.CalendarMonth
    "code" -> Icons.Outlined.Code
    "book" -> Icons.AutoMirrored.Outlined.MenuBook
    "bug" -> Icons.Outlined.BugReport
    "idea" -> Icons.Outlined.Lightbulb
    "star" -> Icons.Outlined.Star
    "home" -> Icons.Outlined.Home
    else -> if (root) Icons.Outlined.Home else Icons.Outlined.Folder
}

/** `#rrggbb`. 형식이 틀리면 null. */
fun parseColor(hex: String?): Color? {
    val digits = hex?.removePrefix("#")?.takeIf { it.length == 6 } ?: return null
    return digits.toLongOrNull(16)?.let { Color(0xFF000000 or it) }
}

val SORTS = listOf(SpaceSort.UPDATED, SpaceSort.CREATED, SpaceSort.TITLE)
