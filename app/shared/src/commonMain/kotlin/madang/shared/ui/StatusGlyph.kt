package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import madang.shared.main.RunGlyph

private val Amber = Color(0xFFD97706)
private val Green = Color(0xFF15803D)
private val Red = Color(0xFFDC2626)
private val Gray = Color(0xFF9CA3AF)

/**
 * 실행 상태 글리프 하나. 카드·실행 블록·지금 탭이 함께 쓴다: 실행 중은 스피너, 사람 필요는 호박색
 * 물음표, 완료는 초록 체크, 실패는 빨간 점, 유휴는 회색 점.
 */
@Composable
fun StatusGlyph(glyph: RunGlyph, modifier: Modifier = Modifier, size: Dp = 14.dp) {
    val label = LocalStrings.current.side.glyph(glyph)
    Box(
        modifier = modifier.size(size).semantics { contentDescription = label },
        contentAlignment = Alignment.Center
    ) {
        when (glyph) {
            RunGlyph.RUNNING -> CircularProgressIndicator(
                modifier = Modifier.size(size * 0.85f),
                strokeWidth = 1.5.dp,
                color = MaterialTheme.colorScheme.primary
            )

            RunGlyph.NEEDS_HUMAN -> Text(
                "?",
                color = Amber,
                fontWeight = FontWeight.Bold,
                fontSize = (size.value * 0.95f).sp
            )

            RunGlyph.DONE -> Icon(
                Icons.Filled.Check,
                contentDescription = null,
                tint = Green,
                modifier = Modifier.size(size)
            )

            RunGlyph.FAILED -> Dot(Red, size * 0.55f)

            RunGlyph.IDLE -> Dot(Gray, size * 0.45f)
        }
    }
}

@Composable
private fun Dot(color: Color, size: Dp) {
    Box(modifier = Modifier.size(size).background(color, CircleShape))
}
