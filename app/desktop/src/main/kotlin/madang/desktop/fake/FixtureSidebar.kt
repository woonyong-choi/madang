package madang.desktop.fake

import java.io.File
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import madang.api.model.FileEntry
import madang.api.model.FileLens
import madang.api.model.FileTree
import madang.api.model.GitStatus
import madang.api.model.ObservedPort
import madang.api.model.Project
import madang.api.model.Usage
import madang.shared.core.CoreClient

/**
 * 픽스처의 사이드바 응답: 파일 트리, 관찰한 포트, 사용량.
 *
 * - `files/<프로젝트 id>.json`: `entries`(FileEntry 배열, 전체 렌즈)와 `runs`(작업 폴더 자체의 실행
 *   대상), `pages`(페이지 id별 이 페이지 렌즈 경로). 없으면 `.madang/`만 있는 트리다.
 * - `ports.json`: 프로젝트 id별 ObservedPort 배열. "선언으로 저장"한 포트는 메모리에서 이름이 붙는다.
 * - `usage.json`: `GET /usage` 응답. 없으면 계약 예시로 답한다.
 */
class FixtureSidebar(private val dir: File) {

    private val json = CoreClient.CoreJson
    private val declared = mutableMapOf<Pair<String, Int>, String>()

    /**
     * [lens]로 거른 파일 트리. 변경됨 렌즈는 [git] 상태의 파일이고, 저장소가 아니면 null(409
     * `no_repo`)이다.
     */
    fun files(project: Project, lens: FileLens, page: String?, git: GitStatus): FileTree? {
        val source = filesOf(project.id)
        val all = source?.get("entries")
            ?.let { json.decodeFromJsonElement(ListSerializer(FileEntry.serializer()), it) }
            ?: listOf(
                FileEntry(".madang", FileEntry.Type.DIR),
                FileEntry(".madang/brief.md", FileEntry.Type.FILE)
            )
        val entries = when (lens) {
            FileLens.ALL -> all

            FileLens.CHANGED -> if (git.repository) {
                git.files.map { FileEntry(it.path, FileEntry.Type.FILE, change = it.code) }
            } else {
                return null
            }

            FileLens.PAGE -> {
                val paths = source?.get("pages")?.jsonObject?.get(page.orEmpty())
                    ?.let { json.decodeFromJsonElement(ListSerializer(String.serializer()), it) }
                    .orEmpty()
                all.filter { it.path in paths }
            }
        }
        val runs = source?.get("runs")
            ?.takeIf { lens == FileLens.ALL }
            ?.let { json.decodeFromJsonElement(ListSerializer(String.serializer()), it) }
            .orEmpty()
        return FileTree(project.path, lens, entries, runs, truncated = false)
    }

    /** 프로젝트에서 관찰한 포트. 선언으로 저장한 포트에는 그 이름이 붙는다. */
    fun ports(project: String): List<ObservedPort> {
        val file = File(dir, "ports.json").takeIf { it.isFile } ?: return emptyList()
        val element = json.parseToJsonElement(file.readText()).jsonObject[project]
            ?: return emptyList()
        return json.decodeFromJsonElement(ListSerializer(ObservedPort.serializer()), element)
            .map { port -> declared[project to port.port]?.let { port.copy(run = it) } ?: port }
    }

    /** 열린 포트를 [name]으로 선언한다. 지금 열려 있지 않으면 null. */
    fun declare(project: String, port: Int, name: String): ObservedPort? {
        if (ports(project).none { it.port == port }) return null
        declared[project to port] = name
        return ports(project).first { it.port == port }
    }

    fun usage(): Usage? = File(dir, "usage.json").takeIf { it.isFile }
        ?.let { json.decodeFromString(Usage.serializer(), it.readText()) }

    private fun filesOf(project: String): JsonObject? =
        File(dir, "files/$project.json").takeIf { it.isFile }
            ?.let { json.parseToJsonElement(it.readText()).jsonObject }
}
