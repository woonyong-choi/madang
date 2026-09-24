package madang.desktop

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/** 엔진 번들 검사: CEF를 띄우기 전에 번들이 앱의 jcef와 짝이 맞는지 파일만 보고 판단한다. */
class WebEngineBundleTest {

    private val dir: File = Files.createTempDirectory("madang-webengine").toFile()

    @AfterTest
    fun cleanUp() {
        dir.deleteRecursively()
    }

    @Test
    fun matchingBundleIsReady() {
        writeMatchingBundle()

        assertEquals(BundleCheck.Ready, macBundle().check())
    }

    @Test
    fun emptyFolderIsAbsent() {
        assertEquals(BundleCheck.Absent, macBundle().check())
        assertEquals(BundleCheck.Absent, macBundle(dir.resolve("missing")).check())
    }

    @Test
    fun remoteOnlyBundleWithoutMarkerIsStale() {
        writeRemoteOnlyBundle()

        assertEquals(BundleCheck.Stale(null), macBundle().check())
    }

    @Test
    fun remoteOnlyBundleFromPinnedReleaseIsBroken() {
        writeRemoteOnlyBundle()
        macBundle().markInstalled()

        val check = assertIs<BundleCheck.Broken>(macBundle().check())
        assertTrue(check.reason.contains("Chromium Embedded Framework.framework"), check.reason)
    }

    @Test
    fun markerFromAnotherReleaseIsStale() {
        writeMatchingBundle()
        dir.resolve(WebEngineBundle.MARKER).writeText("jbr-release-25.0.4.1b610.67")

        assertEquals(BundleCheck.Stale("jbr-release-25.0.4.1b610.67"), macBundle().check())
    }

    @Test
    fun libraryNeedingUnknownClassesIsBroken() {
        writeMatchingBundle()
        writeLibrary(KNOWN + "org/cef/misc/LongRef")

        val check = assertIs<BundleCheck.Broken>(macBundle().check())
        assertTrue(check.reason.contains("org/cef/misc/LongRef"), check.reason)
    }

    @Test
    fun referencedClassesAreWholeNulTerminatedNames() {
        val library = dir.resolve("libjcef.dylib")
        library.writeBytes(
            "\u0000org/cef/CefApp\u0000(Lorg/cef/browser/CefBrowser;)V\u0000org/cef/\u0000"
                .toByteArray(Charsets.ISO_8859_1)
        )

        assertEquals(setOf("org/cef/CefApp"), WebEngineBundle.referencedClasses(library))
    }

    @Test
    fun removeDeletesOnlyTheBundleFolder() {
        val bundleDir = dir.resolve("kcef-bundle")
        val sibling = dir.resolve("settings.json").apply { writeText("{}") }
        bundleDir.mkdirs()
        bundleDir.resolve(WebEngineBundle.INSTALL_LOCK).writeText("")

        macBundle(bundleDir).remove()

        assertFalse(bundleDir.exists())
        assertTrue(sibling.isFile)
    }

    @Test
    fun appCarriesTheClassesThePinnedLibraryNeeds() {
        // 앱 클래스패스에 jcef jar가 있다. 기본 클래스 확인이 실제 클래스를 찾는다.
        writeMatchingBundle()

        assertEquals(BundleCheck.Ready, WebEngineBundle(dir, os = MAC).check())
    }

    @Test
    fun macArgsPointCefAtTheBundleNotTheJavaRuntime() {
        val frameworks = dir.canonicalFile.resolve("Frameworks")
        val args = macBundle().cefArgs()

        assertEquals(
            listOf(
                "--framework-dir-path=$frameworks/Chromium Embedded Framework.framework",
                "--main-bundle-path=$frameworks/jcef Helper.app",
                "--browser-subprocess-path=$frameworks/jcef Helper.app/Contents/MacOS/jcef Helper"
            ),
            args.filter { it.endsWith(".framework") || it.contains("Helper") }
        )
        val javaHome = System.getProperty("java.home")
        assertTrue(args.none { it.contains(javaHome) })
    }

    @Test
    fun otherSystemsGetNoPathArgs() {
        val args = WebEngineBundle(dir, os = "Linux", hasClass = KNOWN::contains).cefArgs()

        assertTrue(args.isNotEmpty())
        assertTrue(args.none { it.contains(dir.name) })
    }

    private fun macBundle(at: File = dir) =
        WebEngineBundle(at, os = MAC, hasClass = KNOWN::contains)

    /** 고정 릴리스 번들처럼: 설치 표식, CEF 프레임워크와 jcef 헬퍼, jar에 있는 클래스만 찾는 라이브러리. */
    private fun writeMatchingBundle() {
        dir.resolve(WebEngineBundle.INSTALL_LOCK).writeText("")
        dir.resolve("Frameworks/Chromium Embedded Framework.framework").mkdirs()
        dir.resolve("Frameworks/jcef Helper.app").mkdirs()
        writeLibrary(KNOWN)
        macBundle().markInstalled()
    }

    /** 최신 릴리스 번들처럼: `Frameworks/`에 `cef_server.app`만 있다. */
    private fun writeRemoteOnlyBundle() {
        dir.resolve(WebEngineBundle.INSTALL_LOCK).writeText("")
        dir.resolve("Frameworks/cef_server.app/Contents/MacOS").mkdirs()
        writeLibrary(KNOWN)
    }

    private fun writeLibrary(classes: Set<String>) {
        val text = classes.joinToString(separator = "\u0000", prefix = "\u0000", postfix = "\u0000")
        dir.resolve("libjcef.dylib").writeBytes(text.toByteArray(Charsets.ISO_8859_1))
    }

    private companion object {
        const val MAC = "Mac OS X"
        val KNOWN = setOf("org/cef/CefApp", "org/cef/browser/CefBrowser", "org/cef/CefSettings")
    }
}
