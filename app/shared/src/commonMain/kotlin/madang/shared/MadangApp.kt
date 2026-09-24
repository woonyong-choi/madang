package madang.shared

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** 앱 루트. 3열(탐색 / 목록 / 본문) 레이아웃. */
@Composable
fun MadangApp() {
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Row(modifier = Modifier.fillMaxSize()) {
                Pane("Navigation", Modifier.width(240.dp).fillMaxHeight())
                VerticalDivider()
                Pane("List", Modifier.width(320.dp).fillMaxHeight())
                VerticalDivider()
                Pane("Content", Modifier.weight(1f).fillMaxHeight())
            }
        }
    }
}

@Composable
private fun Pane(label: String, modifier: Modifier) {
    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
