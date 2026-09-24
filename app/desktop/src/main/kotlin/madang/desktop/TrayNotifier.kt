package madang.desktop

import java.awt.GraphicsEnvironment
import java.awt.SystemTray
import java.awt.TrayIcon
import javax.imageio.ImageIO
import madang.shared.Notifier

/**
 * 운영체제 알림 영역(macOS 알림 센터, Windows 알림)으로 알린다. 알림 아이콘은 처음 알릴 때 한 번
 * 올린다. 알림 영역이 없는 환경이면 아무것도 하지 않는다.
 */
class TrayNotifier : Notifier {
    private var icon: TrayIcon? = null

    override fun notify(title: String, body: String) {
        val tray = trayIcon() ?: return
        tray.displayMessage(title, body, TrayIcon.MessageType.INFO)
    }

    @Synchronized
    private fun trayIcon(): TrayIcon? {
        icon?.let { return it }
        if (GraphicsEnvironment.isHeadless() || !SystemTray.isSupported()) return null
        val image = Thread.currentThread().contextClassLoader.getResource("icon.png")
            ?.let(ImageIO::read) ?: return null
        return runCatching {
            TrayIcon(image, "Madang").apply {
                isImageAutoSize = true
                SystemTray.getSystemTray().add(this)
            }
        }.onFailure { System.err.println("madang: cannot show notifications: ${it.message}") }
            .getOrNull()
            ?.also { icon = it }
    }

    /** 올린 알림 아이콘을 내린다. */
    fun dispose() {
        icon?.let { SystemTray.getSystemTray().remove(it) }
        icon = null
    }
}
