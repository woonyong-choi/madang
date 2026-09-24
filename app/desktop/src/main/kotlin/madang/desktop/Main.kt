package madang.desktop

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.graphics.painter.BitmapPainter
import androidx.compose.ui.graphics.toComposeImageBitmap
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.io.File
import kotlin.system.exitProcess
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChangedBy
import kotlinx.coroutines.flow.filterIsInstance
import kotlinx.coroutines.flow.first
import madang.desktop.fake.ContractExamples
import madang.desktop.fake.FakeCore
import madang.desktop.fake.FixtureHome
import madang.shared.AppDependencies
import madang.shared.AppViewModel
import madang.shared.MadangApp
import madang.shared.Screen
import madang.shared.core.CoreClient
import madang.shared.settings.AppSettings
import madang.shared.settings.InMemorySettingsStore
import org.jetbrains.skia.Image

/** MADANG_SMOKE=1이면 첫 프레임을 그린 뒤 [smokeSeconds]초 뒤 스스로 종료한다. */
private val smokeMode = System.getenv("MADANG_SMOKE") == "1"

/** 종료까지 기다리는 초. MADANG_SMOKE_SECONDS로 바꾼다(문서 탭 진단은 엔진을 띄울 시간이 든다). */
private val smokeSeconds = System.getenv("MADANG_SMOKE_SECONDS")?.toLongOrNull() ?: 3L

/** MADANG_OPEN_PAGE=<페이지 id>면 메인 화면이 뜨는 대로 그 페이지를 연다(문서 탭 진단). */
private val pageAtStart: String? = System.getenv("MADANG_OPEN_PAGE")

/** MADANG_FAKE_CORE=1이면 계약 예시로 답하는 가짜 core에 붙는다. */
private val fakeCoreMode = System.getenv("MADANG_FAKE_CORE") == "1"

/** 브라우저 탭·문서 탭 엔진. 번들과 렌더러는 앱 설정 폴더 아래에 둔다. */
private val documentRuntime =
    DocumentRuntime(DesktopPaths.appConfigDir().resolve("document-runtime"))
private val browser = KcefBrowserEngine(
    WebEngineBundle(DesktopPaths.appConfigDir().resolve("kcef-bundle")),
    documentRuntime
)

/** run 완료·묻는 블록 시스템 알림. */
private val notifier = TrayNotifier()

/** 이 인자로 띄우면 창 없이 엔진 번들만 검사해 결과를 찍고 끝낸다(0 맞음, 1 맞지 않음). */
private const val CHECK_WEB_ENGINE = "--check-webengine"

/** 이 인자로 띄우면 앱 화면 없이 CEF를 띄워 로컬 html을 읽어 보고 끝낸다([WebEngineProbe]). */
private const val PROBE_WEB_ENGINE = "--probe-webengine"

fun main(args: Array<String>) {
    when (args.firstOrNull()) {
        CHECK_WEB_ENGINE -> exitProcess(checkWebEngine())
        PROBE_WEB_ENGINE -> exitProcess(probeWebEngine())
        else -> runApp()
    }
}

/** 엔진 번들을 검사한다. CEF는 띄우지 않는다. 확인 스크립트가 설치된 앱으로 부른다. */
private fun checkWebEngine(): Int {
    val bundle = WebEngineBundle(DesktopPaths.appConfigDir().resolve("kcef-bundle"))
    val check = bundle.check()
    println("madang: web engine bundle ${bundle.dir.path}")
    println("madang: expected release ${WebEngineBundle.RELEASE}")
    println("madang: check ${WebEngineBundle.describe(check)}")
    return if (check == BundleCheck.Ready) 0 else 1
}

/** CEF를 띄워 본다. 확인 스크립트의 probe가 설치된 앱으로 부른다. */
private fun probeWebEngine(): Int {
    val code = WebEngineProbe(browser, documentRuntime).run()
    browser.dispose()
    println("madang: probe exit $code")
    return code
}

private fun runApp() = application {
    val icon = remember { windowIcon() }
    val scope = rememberCoroutineScope()
    val app = remember { AppViewModel(dependencies(), scope) }
    val exit = {
        browser.dispose()
        notifier.dispose()
        exitApplication()
    }
    Window(
        onCloseRequest = exit,
        title = "Madang",
        icon = icon,
        state = rememberWindowState(size = DpSize(1280.dp, 800.dp))
    ) {
        MadangApp(app)

        LaunchedEffect(Unit) {
            browser.status.distinctUntilChangedBy { it::class }
                .collect { println("madang: web engine $it") }
        }
        pageAtStart?.let { page ->
            LaunchedEffect(page) {
                val main = app.screen.filterIsInstance<Screen.Main>().first()
                println("madang: opening page $page (MADANG_OPEN_PAGE)")
                main.viewModel.openPage(page, advance = true)
            }
        }
        if (smokeMode) {
            LaunchedEffect(Unit) {
                withFrameNanos { }
                println("madang: first frame rendered, exiting in ${smokeSeconds}s (smoke mode)")
                delay(smokeSeconds * 1_000)
                println("madang: screen at exit: ${app.screen.value::class.simpleName}")
                exit()
            }
        }
    }
}

private fun dependencies(): AppDependencies {
    if (fakeCoreMode) return fakeDependencies()
    return AppDependencies(
        settings = FileSettingsStore(DesktopPaths.appConfigDir().resolve("settings.json")),
        claudeProbe = CommandClaudeProbe(),
        toolLocator = ShellToolLocator(),
        portFile = { CorePortFile(DesktopPaths.appHome(it)) },
        launcher = { ProcessCoreLauncher(it) },
        folderPicker = DesktopFolderPicker(),
        localFiles = DesktopLocalFiles(),
        browser = browser,
        notifier = notifier
    )
}

/**
 * 가짜 core는 떠 있는 core처럼 기본 주소에서 답한다. 앱 설정 파일은 건드리지 않는다.
 * `MADANG_FAKE_FIXTURE=<폴더>`면 그 픽스처로 프로젝트·페이지에 답하고 메인부터 시작한다.
 */
private fun fakeDependencies(): AppDependencies {
    val spec = File(System.getProperty("madang.openapiSpec") ?: "../core/openapi.yaml")
    val fixture = System.getenv("MADANG_FAKE_FIXTURE")?.let { FixtureHome(File(it)) }
    val fake = FakeCore(
        ContractExamples.load(spec),
        homeReady = fixture != null || System.getenv("MADANG_FAKE_HOME") == "1",
        fixture = fixture
    )
    println("madang: using fake core from ${spec.path}")
    return AppDependencies(
        settings = InMemorySettingsStore(),
        claudeProbe = CommandClaudeProbe(),
        toolLocator = ShellToolLocator(),
        portFile = { { null } },
        launcher = null,
        connect = { CoreClient(it, fake.engine) },
        eventTransport = { fake.events },
        folderPicker = DesktopFolderPicker(),
        localFiles = DesktopLocalFiles(),
        browser = browser,
        notifier = notifier
    )
}

private fun windowIcon(): BitmapPainter {
    val bytes = checkNotNull(Thread.currentThread().contextClassLoader.getResource("icon.png"))
        .readBytes()
    return BitmapPainter(Image.makeFromEncoded(bytes).toComposeImageBitmap())
}
