package madang.desktop

import java.awt.FileDialog
import java.awt.Frame
import java.io.File
import javax.swing.JFileChooser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.swing.Swing
import kotlinx.coroutines.withContext
import madang.shared.FolderPicker

/**
 * 운영체제의 폴더 선택 대화상자. macOS는 네이티브 `FileDialog`를 폴더 모드로, 그 밖은
 * `JFileChooser`의 폴더 전용 모드를 쓴다.
 */
class DesktopFolderPicker : FolderPicker {

    override suspend fun pick(title: String): String? = withContext(Dispatchers.Swing) {
        if (isMac) pickWithFileDialog(title) else pickWithChooser(title)
    }

    private fun pickWithFileDialog(title: String): String? {
        System.setProperty(MAC_FOLDER_MODE, "true")
        try {
            val dialog = FileDialog(null as Frame?, title, FileDialog.LOAD)
            dialog.isVisible = true
            val name = dialog.file ?: return null
            return File(dialog.directory, name).absolutePath
        } finally {
            System.setProperty(MAC_FOLDER_MODE, "false")
        }
    }

    private fun pickWithChooser(title: String): String? {
        val chooser = JFileChooser().apply {
            dialogTitle = title
            fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
        }
        if (chooser.showOpenDialog(null) != JFileChooser.APPROVE_OPTION) return null
        return chooser.selectedFile?.absolutePath
    }

    private companion object {
        const val MAC_FOLDER_MODE = "apple.awt.fileDialogForDirectories"
        val isMac = System.getProperty("os.name").lowercase().contains("mac")
    }
}
