package madang.shared

import androidx.compose.runtime.staticCompositionLocalOf

/** 플랫폼의 폴더 선택 대화상자. 고른 폴더의 절대 경로를, 취소하면 null을 돌려준다. */
fun interface FolderPicker {
    suspend fun pick(title: String): String?
}

/** 폴더를 고를 수 없는 플랫폼. 항상 취소한 것으로 본다. */
val NoFolderPicker = FolderPicker { null }

/** 화면에서 쓰는 폴더 선택기. [MadangApp]이 플랫폼의 것으로 채운다. */
val LocalFolderPicker = staticCompositionLocalOf { NoFolderPicker }
