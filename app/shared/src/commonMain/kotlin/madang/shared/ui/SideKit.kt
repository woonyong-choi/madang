package madang.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** 사이드바 탭 안의 절 제목. */
@Composable
internal fun SideHeading(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.labelLarge,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier.padding(top = 4.dp, bottom = 4.dp)
    )
}

/** 사이드바 탭 안의 흐린 안내 한 줄. */
@Composable
internal fun SideNote(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(vertical = 4.dp)
    )
}

/** 사이드바 탭 안의 오류 한 줄. */
@Composable
internal fun SideError(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.error,
        modifier = Modifier.padding(vertical = 4.dp)
    )
}

/** 작은 배지 버튼(파일 탭의 "실행"). */
@Composable
internal fun SideBadge(text: String, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = colors.onTertiaryContainer,
        modifier = Modifier
            .padding(start = 6.dp)
            .background(colors.tertiaryContainer, RoundedCornerShape(4.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 6.dp, vertical = 1.dp)
    )
}
