package madang.shared

import androidx.compose.runtime.staticCompositionLocalOf

/** 운영체제의 시스템 알림. 앱 설정에서 끌 수 있다. */
interface Notifier {
    /** 알림을 띄운다. 플랫폼이 알림 누름을 알려 주면 [onClick]을 부른다. */
    fun notify(title: String, body: String, onClick: () -> Unit = {})
}

/** 알림을 띄울 수 없는 플랫폼. */
object NoNotifier : Notifier {
    override fun notify(title: String, body: String, onClick: () -> Unit) = Unit
}

/** 화면이 시스템 알림을 띄우는 곳. */
val LocalNotifier = staticCompositionLocalOf<Notifier> { NoNotifier }
