package madang.shared

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** 브라우저 엔진의 준비 상태. */
sealed interface BrowserStatus {
    /** 아직 준비를 시작하지 않았다. 브라우저 탭을 처음 열 때 시작한다. */
    data object Idle : BrowserStatus

    /** 첫 실행이라 엔진 번들을 내려받는 중. [percent]는 0~100, 모르면 음수. */
    data class Downloading(val percent: Float) : BrowserStatus

    /** 내려받은 번들을 풀거나 엔진을 띄우는 중. */
    data object Installing : BrowserStatus

    data object Ready : BrowserStatus

    /** 설치는 끝났고 앱을 다시 시작해야 쓸 수 있다. */
    data object RestartRequired : BrowserStatus

    data class Failed(val message: String?) : BrowserStatus

    /** 이 플랫폼에는 브라우저 엔진이 없다. */
    data object Unavailable : BrowserStatus
}

/** 브라우저 탭과 문서 탭이 쓰는 웹 엔진. 데스크톱은 KCEF(Chromium)다. */
interface BrowserEngine {
    val status: StateFlow<BrowserStatus>

    /** 엔진을 준비한다. 첫 실행이면 번들을 내려받는다. 이미 시작했으면 아무것도 하지 않는다. */
    fun prepare()

    /** 엔진 번들을 지우고 다시 받는다. [status]가 [BrowserStatus.Failed]일 때만 한다. */
    fun reinstall() = Unit

    /**
     * [url]을 보이는 웹 화면. [status]가 [BrowserStatus.Ready]일 때만 부른다. [reload]가 바뀌면
     * 같은 주소를 다시 읽는다.
     */
    @Composable
    fun Page(url: String, reload: Int, modifier: Modifier)

    /**
     * 렌더러 호스트(`templates/_runtime/app.html`)를 띄우고 [payload]를 `madangApp.render()`로
     * 그리는 웹 화면. [payload]가 바뀌면 같은 화면에서 다시 그린다. 호스트가 앱 요청 주소
     * (`madang-app://…`)로 탐색하면 막고 [onRequest]에 그 주소를 넘긴다. [status]가
     * [BrowserStatus.Ready]일 때만 부른다.
     */
    @Composable
    fun Document(payload: String, onRequest: (String) -> Unit, modifier: Modifier)
}

/**
 * 브라우저 엔진이 없는 플랫폼. 브라우저 탭은 주소와 "외부 브라우저로 열기"만, 문서 탭은 원문만
 * 보인다.
 */
object NoBrowserEngine : BrowserEngine {
    override val status: StateFlow<BrowserStatus> = MutableStateFlow(BrowserStatus.Unavailable)

    override fun prepare() = Unit

    @Composable
    override fun Page(url: String, reload: Int, modifier: Modifier) = Unit

    @Composable
    override fun Document(payload: String, onRequest: (String) -> Unit, modifier: Modifier) = Unit
}

/** 화면에서 쓰는 브라우저 엔진. [MadangApp]이 플랫폼의 것으로 채운다. */
val LocalBrowserEngine = staticCompositionLocalOf<BrowserEngine> { NoBrowserEngine }
