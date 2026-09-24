package madang.shared.core

import kotlin.test.Test
import kotlin.test.assertEquals

class UnknownFilesTest {

    @Test
    fun pathBecomesOneEncodedSegment() {
        assertEquals("blocks%2Fnotes.txt", encodePathSegment("blocks/notes.txt"))
        assertEquals("repo%3Asrc%2Fscratch.ts", encodePathSegment("repo:src/scratch.ts"))
        assertEquals("a%20b%25", encodePathSegment("a b%"))
        assertEquals("%ED%91%9C-1_~.md", encodePathSegment("표-1_~.md"))
    }
}
