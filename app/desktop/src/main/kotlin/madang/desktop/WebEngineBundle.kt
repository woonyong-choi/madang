package madang.desktop

import java.io.File

/** 엔진 번들 검사 결과. */
sealed interface BundleCheck {
    /** 고정 릴리스에서 받았고 필요한 파일과 클래스가 모두 있다. CEF를 띄워도 된다. */
    data object Ready : BundleCheck

    /** 설치를 마친 번들이 없다(`install.lock` 없음). 처음이거나 받다 멈췄다. */
    data object Absent : BundleCheck

    /** 고정 릴리스에서 받았다는 표식이 없거나 다르다. [release]는 표식에 적힌 릴리스. */
    data class Stale(val release: String?) : BundleCheck

    /** 고정 릴리스에서 받았는데 필요한 파일이나 클래스가 없다. */
    data class Broken(val reason: String) : BundleCheck
}

/**
 * 웹 엔진(KCEF) 번들. CEF를 띄우기 전에 [dir]의 번들이 앱에 실린 jcef jar와 짝이 맞는지 파일만
 * 보고 확인한다. 짝이 맞지 않는 번들로 CEF를 띄우면 네이티브 라이브러리가 jar에 없는 클래스를
 * 찾다가 앱이 통째로 죽는다.
 *
 * 번들은 KCEF가 [RELEASE]에서 내려받아 푼 것이다. 받은 뒤 [markInstalled]로 그 릴리스를 [MARKER]에
 * 적어 두고, 다음 실행부터는 이 표식과 파일로 판단한다.
 *
 * @param os `os.name` 값. 운영체제마다 네이티브 라이브러리 이름과 필요한 파일이 다르다.
 * @param hasClass 앱이 그 클래스(`org/cef/...` 꼴 내부 이름)를 갖고 있는지.
 */
class WebEngineBundle(
    val dir: File,
    os: String = System.getProperty("os.name"),
    private val hasClass: (String) -> Boolean = ::appHasClass
) {
    private val isMac = os.lowercase().contains("mac")

    /** jcef 네이티브 라이브러리 파일 이름. */
    val nativeLibrary: String = when {
        isMac -> "libjcef.dylib"
        os.lowercase().contains("win") -> "jcef.dll"
        else -> "libjcef.so"
    }

    fun check(): BundleCheck {
        if (!dir.resolve(INSTALL_LOCK).isFile) return BundleCheck.Absent
        val release = dir.resolve(MARKER).takeIf { it.isFile }?.readText()?.trim()
        if (release != RELEASE) return BundleCheck.Stale(release)
        val missing = requiredFiles().filterNot { dir.resolve(it).exists() }
        if (missing.isNotEmpty()) {
            return BundleCheck.Broken("missing ${missing.joinToString()}")
        }
        val unknown = referencedClasses(dir.resolve(nativeLibrary)).filterNot(hasClass)
        if (unknown.isNotEmpty()) {
            return BundleCheck.Broken(
                "$nativeLibrary needs classes missing from the app: " +
                    unknown.sorted().take(SHOWN_CLASSES).joinToString()
            )
        }
        return BundleCheck.Ready
    }

    /**
     * CEF 명령줄 인자. KCEF 기본 인자(JCefAppConfig)는 JetBrains Runtime 구성이라 CEF 프레임워크와
     * 헬퍼를 `java.home/../Frameworks`에서 찾는데, 앱 런타임에는 그곳에 CEF가 없다. 그래서 macOS는
     * 경로 인자를 이 번들 기준으로 직접 준다. 이 인자는 두 곳에 쓴다. JCEF는 `--framework-dir-path`가
     * 여럿이면 마지막 것으로 CEF 프레임워크를 싣고, CEF는 앱 처리기가 넘긴 인자에서 프레임워크(ICU
     * 데이터·리소스)와 헬퍼를 찾는다. 나머지는 KCEF 기본 인자의 경로 아닌 인자다.
     */
    fun cefArgs(): List<String> {
        if (!isMac) return COMMON_ARGS
        val frameworks = dir.canonicalFile.resolve("Frameworks")
        val helper = frameworks.resolve(MAC_HELPER)
        return listOf(
            "--framework-dir-path=${frameworks.resolve(MAC_FRAMEWORK).path}",
            "--main-bundle-path=${helper.path}",
            "--browser-subprocess-path=${helper.resolve(MAC_HELPER_EXECUTABLE).path}"
        ) + COMMON_ARGS
    }

    /** 방금 [RELEASE]에서 받은 번들이라고 표식을 남긴다. */
    fun markInstalled() {
        dir.resolve(MARKER).writeText(RELEASE)
    }

    /** 번들 폴더를 지운다. 앱 설정 폴더 안의 번들 폴더만 지운다. */
    fun remove() {
        dir.deleteRecursively()
    }

    /**
     * macOS 번들의 `Frameworks/`는 CEF 프레임워크와 jcef 헬퍼를 담아야 한다. 원격(별도 프로세스)
     * 구성 번들은 `cef_server.app`만 있어 이 jcef와 맞지 않는다. 다른 운영체제는 네이티브
     * 라이브러리만 본다.
     */
    private fun requiredFiles(): List<String> =
        listOf(nativeLibrary) + if (isMac) MAC_FRAMEWORKS else emptyList()

    companion object {
        /**
         * 고정한 엔진 번들 릴리스(JetBrains Runtime). KCEF 2025.03.23 릴리스 노트가 이 jcef와 맞는다고
         * 적은 릴리스다. 정하지 않으면 KCEF는 최신 릴리스를 받는데, 그 번들은 이 jcef와 맞지 않는다.
         */
        const val RELEASE = "jbr-release-17.0.14b1367.22"

        /** 번들을 받은 릴리스를 적어 두는 파일. */
        const val MARKER = "madang-webengine-release"

        /** KCEF가 설치를 마치면 만드는 파일. */
        const val INSTALL_LOCK = "install.lock"

        private const val MAC_FRAMEWORK = "Chromium Embedded Framework.framework"
        private const val MAC_HELPER = "jcef Helper.app"
        private const val MAC_HELPER_EXECUTABLE = "Contents/MacOS/jcef Helper"
        private val MAC_FRAMEWORKS = listOf("Frameworks/$MAC_FRAMEWORK", "Frameworks/$MAC_HELPER")
        private val COMMON_ARGS = listOf(
            "--disable-in-process-stack-traces",
            "--use-mock-keychain",
            "--disable-features=SpareRendererForSitePerProcess"
        )
        private const val SHOWN_CLASSES = 3
        private val CLASS_NAME = Regex("(?<=\u0000)org/cef/[A-Za-z0-9_/$]+(?=\u0000)")

        /** 검사 결과를 한 줄로. 준비 실패 알림에 이유로 보인다. */
        fun describe(check: BundleCheck): String = when (check) {
            BundleCheck.Ready -> "ready"

            BundleCheck.Absent -> "bundle is not installed"

            is BundleCheck.Stale ->
                check.release?.let { "bundle release $it is not $RELEASE" }
                    ?: "bundle has no release marker"

            is BundleCheck.Broken -> check.reason
        }

        /** 네이티브 라이브러리가 JNI로 찾는 `org/cef/` 클래스 이름(NUL로 끝나는 문자열). */
        fun referencedClasses(library: File): Set<String> {
            val text = String(library.readBytes(), Charsets.ISO_8859_1)
            return CLASS_NAME.findAll(text).map { it.value }.toSet()
        }

        private fun appHasClass(name: String): Boolean =
            WebEngineBundle::class.java.classLoader.getResource("$name.class") != null
    }
}
