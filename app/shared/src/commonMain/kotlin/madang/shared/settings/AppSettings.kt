package madang.shared.settings

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import madang.shared.main.TabSet

@Serializable
enum class Language {
    @SerialName("ko")
    KO,

    @SerialName("en")
    EN
}

/**
 * 앱 설정. 앱이 쓰는 유일한 파일이며 문서는 담지 않는다.
 *
 * @property coreUrl 사용자가 지정한 core 주소. null이면 `core.port`와 기본 주소로 찾는다.
 * @property coreBinary core 실행 파일 경로. null이면 개발 방식이나 동봉 파일로 띄운다.
 * @property homePath 앱 홈 경로. null이면 core 기본값(`~/.madang`).
 * @property pageTabs 페이지 id별로 가운데 열에 열어 둔 탭. 재시작 뒤에도 페이지마다 되살린다.
 * @property notifications run 완료·실패와 묻는 블록을 시스템 알림으로 알린다.
 * @property unread run이 끝났지만 아직 열어 보지 않은 페이지 id. 재시작 뒤에도 카드가 굵게 남는다.
 */
@Serializable
data class AppSettings(
    val coreUrl: String? = null,
    val coreBinary: String? = null,
    val homePath: String? = null,
    val language: Language = Language.KO,
    val pageTabs: Map<String, TabSet> = emptyMap(),
    val notifications: Boolean = true,
    val unread: Set<String> = emptySet()
)

/** 앱 설정을 읽고 쓴다. 플랫폼마다 저장 위치가 다르다. */
interface AppSettingsStore {
    fun load(): AppSettings

    fun save(settings: AppSettings)
}

/** 메모리에만 두는 설정. 테스트와 가짜 core 실행에 쓴다. */
class InMemorySettingsStore(private var current: AppSettings = AppSettings()) :
    AppSettingsStore {
    override fun load(): AppSettings = current

    override fun save(settings: AppSettings) {
        current = settings
    }
}
