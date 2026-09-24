package madang.desktop

import java.io.File

/**
 * 문서 탭 렌더러(`templates/_runtime`의 호스트와 렌더러). 빌드가 jar의 `madang-runtime/`에 싣고,
 * WebView가 `file://`로 열 수 있게 [dir]에 풀어 둔다. 게시 사이트와 같은 파일이다.
 */
class DocumentRuntime(private val dir: File) {

    /** 호스트 페이지(`app.html`). [install] 뒤에 있다. */
    val host: File get() = dir.resolve(HOST)

    /** jar의 렌더러 파일을 [dir]에 맞춘다. 내용이 같으면 쓰지 않는다. */
    fun install(): File {
        for (name in FILES) {
            val bytes = checkNotNull(javaClass.classLoader.getResource("$RESOURCE_DIR/$name")) {
                "renderer file $name is missing from the app"
            }.readBytes()
            val target = dir.resolve(name)
            if (!target.isFile || !target.readBytes().contentEquals(bytes)) {
                target.parentFile.mkdirs()
                target.writeBytes(bytes)
            }
        }
        return host
    }

    companion object {
        private const val RESOURCE_DIR = "madang-runtime"
        private const val HOST = "app.html"

        /** 싣는 파일. `build.gradle.kts`의 목록과 같다. */
        val FILES = listOf(
            HOST,
            "app.js",
            "document.js",
            "document.css",
            "vendor/marked.umd.js",
            "vendor/marked.LICENSE",
            "THIRD_PARTY_NOTICES.md"
        )
    }
}
