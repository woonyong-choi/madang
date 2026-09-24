package madang.shared

import madang.shared.core.CoreClient
import madang.shared.core.CoreLauncher
import madang.shared.core.EventTransport
import madang.shared.core.PortFileReader
import madang.shared.core.WebSocketEventTransport
import madang.shared.onboarding.ToolProbe
import madang.shared.settings.AppSettings
import madang.shared.settings.AppSettingsStore

/**
 * 플랫폼이 앱에 넘기는 것들.
 *
 * @property connect core 주소로 클라이언트를 만든다. 가짜 core는 여기서 MockEngine을 끼운다.
 * @property portFile 설정의 앱 홈에서 `core.port`를 읽는 방법.
 * @property launcher core를 띄우는 방법. core를 띄울 수 없는 플랫폼은 null.
 * @property eventTransport 연결에서 이벤트를 받는 방법.
 */
class AppDependencies(
    val settings: AppSettingsStore,
    val toolProbe: ToolProbe,
    val portFile: (AppSettings) -> PortFileReader,
    val launcher: ((AppSettings) -> CoreLauncher)?,
    val connect: (baseUrl: String) -> CoreClient = { CoreClient(it) },
    val eventTransport: (CoreClient) -> EventTransport = {
        WebSocketEventTransport(it.http, it.baseUrl)
    }
)
