package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class DiffTest {

    private val text = """
        diff --git a/src/session/refresh.ts b/src/session/refresh.ts
        index 3f2a1c0..9b7e4d2 100644
        --- a/src/session/refresh.ts
        +++ b/src/session/refresh.ts
        @@ -10,3 +10,4 @@ export async function refresh(
         const a = 1
        -const b = 2
        +const b = 3
        +const c = 4
         const d = 5
        diff --git a/src/lock.ts b/src/lock.ts
        new file mode 100644
        --- /dev/null
        +++ b/src/lock.ts
        @@ -0,0 +1,2 @@
        +export {}
        +export const lock = 1
        \ No newline at end of file
        diff --git a/old.ts b/old.ts
        deleted file mode 100644
        --- a/old.ts
        +++ /dev/null
        @@ -1 +0,0 @@
        -gone
        diff --git a/a/name.md b/b/name.md
        similarity index 100%
        rename from a/name.md
        rename to b/name.md
        diff --git a/logo.png b/logo.png
        Binary files a/logo.png and b/logo.png differ
    """.trimIndent() + "\n"

    @Test
    fun splitsTheDiffByFile() {
        val files = parseDiff(text)

        assertEquals(
            listOf("src/session/refresh.ts", "src/lock.ts", "old.ts", "b/name.md", "logo.png"),
            files.map { it.path }
        )
        assertEquals(
            listOf(
                DiffFile.Change.MODIFIED,
                DiffFile.Change.ADDED,
                DiffFile.Change.DELETED,
                DiffFile.Change.RENAMED,
                DiffFile.Change.MODIFIED
            ),
            files.map { it.change }
        )
        assertEquals(
            listOf(2 to 1, 2 to 0, 0 to 1, 0 to 0, 0 to 0),
            files.map {
                it.added to
                    it.removed
            }
        )
        assertEquals("a/name.md", files[3].oldPath)
        assertTrue(files[4].binary)
    }

    @Test
    fun linesCarryOldAndNewNumbers() {
        val lines = parseDiff(text).first().lines

        assertEquals(DiffLine.Kind.HUNK, lines[0].kind)
        assertEquals(DiffLine(DiffLine.Kind.CONTEXT, "const a = 1", 10, 10), lines[1])
        assertEquals(DiffLine(DiffLine.Kind.REMOVED, "const b = 2", 11, null), lines[2])
        assertEquals(DiffLine(DiffLine.Kind.ADDED, "const b = 3", null, 11), lines[3])
        assertEquals(DiffLine(DiffLine.Kind.ADDED, "const c = 4", null, 12), lines[4])
        assertEquals(DiffLine(DiffLine.Kind.CONTEXT, "const d = 5", 12, 13), lines[5])
    }

    @Test
    fun noteLinesAndEmptyDiff() {
        val added = parseDiff(text)[1]
        assertEquals(DiffLine.Kind.NOTE, added.lines.last().kind)
        assertEquals(emptyList(), parseDiff(""))
        assertEquals(emptyList(), parseDiff("warning: something\n"))
    }
}
