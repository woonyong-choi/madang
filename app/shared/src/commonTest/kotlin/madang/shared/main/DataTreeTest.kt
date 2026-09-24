package madang.shared.main

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class DataTreeTest {

    private val yaml = """
        name: 김마당
        work:
          - company: 펄어비스
            period: "2019"
          - company: 한빛
        skills: [Kotlin, Go]
        note: ~
    """.trimIndent()

    @Test
    fun formatComesFromTheExtension() {
        assertEquals(DataFormat.JSON, dataFormatOf("blocks/b05-base.json"))
        assertEquals(DataFormat.YAML, dataFormatOf("config.yaml"))
        assertEquals(DataFormat.YAML, dataFormatOf("ci.YML"))
        assertEquals(DataFormat.CSV, dataFormatOf("incidents.csv"))
        assertNull(dataFormatOf("notes.md"))
    }

    @Test
    fun yamlJsonAndCsvBecomeTheSameTree() {
        val fromYaml = parseData(yaml, DataFormat.YAML)
        val fromJson = parseData(
            """{"name":"김마당","work":[{"company":"펄어비스","period":"2019"},{"company":"한빛"}],
            |"skills":["Kotlin","Go"],"note":null}
            """.trimMargin(),
            DataFormat.JSON
        )
        assertEquals(fromJson, fromYaml)

        assertEquals(
            DataNode.Sequence(
                listOf(
                    DataNode.Mapping(
                        listOf("a" to DataNode.Scalar("1"), "b" to DataNode.Scalar("2"))
                    )
                )
            ),
            parseData("a,b\n1,2\n", DataFormat.CSV)
        )
    }

    @Test
    fun brokenContentIsNotParsed() {
        assertNull(parseData("{", DataFormat.JSON))
        assertNull(parseData("a: [", DataFormat.YAML))
        assertNull(dataPreview("a: [", DataFormat.YAML))
    }

    @Test
    fun yamlMappingBecomesKeyValueTable() {
        val table = dataPreview(yaml, DataFormat.YAML)!!

        assertEquals(listOf("key", "value"), table.columns)
        assertEquals(listOf("work", "[2]"), table.rows[1])
        assertEquals(listOf("note", ""), table.rows[3])
    }

    @Test
    fun treeRowsFollowTheExpandedSet() {
        val root = parseData(yaml, DataFormat.YAML)!!

        val collapsed = treeRows(root, emptySet())
        assertEquals(listOf("name", "work", "skills", "note"), collapsed.map { it.label })
        assertEquals(
            TreeRow("$/work", 0, "work", "[2]", expandable = true, expanded = false),
            collapsed[1]
        )

        val open = treeRows(root, setOf("$/work", "$/work/0"))
        assertEquals(
            listOf("name", "work", "0", "company", "period", "1", "skills", "note"),
            open.map { it.label }
        )
        assertEquals(2, open[3].depth)
        assertEquals("펄어비스", open[3].summary)
    }

    @Test
    fun twoLevelsAreExpandedAtFirst() {
        val root = parseData(yaml, DataFormat.YAML)!!

        assertEquals(setOf("$/work", "$/work/0", "$/work/1", "$/skills"), initiallyExpanded(root))
    }
}
