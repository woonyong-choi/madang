package madang.shared

/**
 * 작업 폴더 파일을 읽고 운영체제의 앱으로 여는 곳. 쓰지 않는다: 파일을 바꾸는 일은 core만 한다.
 */
interface LocalFiles {
    /** [path](절대 경로) 파일의 내용. 읽을 수 없으면 예외를 던진다. */
    suspend fun read(path: String): String

    /** [target]을 운영체제의 기본 앱으로 연다. 파일 경로는 편집기, URL은 브라우저로. */
    fun openExternally(target: String)
}

/** 파일을 읽을 수 없는 플랫폼. */
object NoLocalFiles : LocalFiles {
    override suspend fun read(path: String): String =
        throw UnsupportedOperationException("local files are not available")

    override fun openExternally(target: String) = Unit
}
