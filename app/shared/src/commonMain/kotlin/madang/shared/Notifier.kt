package madang.shared

import androidx.compose.runtime.staticCompositionLocalOf

/** 운영체제의 시스템 알림. 앱 설정에서 끌 수 있다. */
interface Notifier {
    fun notify(title: String, body: String)
}

/** 알림을 띄울 수 없는 플랫폼. */
object NoNotifier : Notifier {
    override fun notify(title: String, body: String) = Unit
}

/** 화면이 시스템 알림을 띄우는 곳. */
val LocalNotifier = staticCompositionLocalOf<Notifier> { NoNotifier }
