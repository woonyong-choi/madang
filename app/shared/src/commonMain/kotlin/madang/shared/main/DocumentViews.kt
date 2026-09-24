package madang.shared.main

import kotlin.coroutines.cancellation.CancellationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import madang.api.model.ViewerStatus
import madang.shared.LocalFiles

/**
 * 문서의 view 펜스를 렌더러 context([ViewEntry])로 푼다.
 *
 * 뷰어는 core 등록부 목록([listViewers], `GET /viewers`)이 선언한 폴더에서 읽는다. pinned면 앱 홈의
 * `cache/<해시>/<이름>/` 사본을 쓴다. 데이터는 문서 폴더 기준 `data=` 파일이다. 짐작하지 않는다:
 * 목록에 없는 이름은 missing, 끊긴 뷰어는 broken, 읽거나 해석할 수 없는 데이터는 invalid다.
 * 데이터 스키마 검사는 core의 일이라 여기서 하지 않는다.
 *
 * @param listViewers 프로젝트 id(없으면 null)로 등록된 뷰어 목록을 받는다. 프로젝트 뷰어가 먼저 온다.
 * @param home 앱 홈 폴더. pinned 사본을 찾을 때만 부른다.
 */
class DocumentViews(
    private val listViewers: suspend (String?) -> List<ViewerStatus>,
    private val home: suspend () -> String,
    private val files: LocalFiles
) {
    /**
     * [markdown]의 view 펜스를 모두 푼다. 펜스가 없으면 core에 묻지 않는다.
     *
     * @param documentDir 문서가 있는 폴더(절대 경로). 모르면 데이터를 읽지 못한다.
     * @param project 문서의 프로젝트 id.
     */
    suspend fun resolve(
        markdown: String,
        documentDir: String?,
        project: String?
    ): Map<String, ViewEntry> {
        val refs = findViews(markdown)
        if (refs.isEmpty()) return emptyMap()
        val viewers = try {
            listViewers(project)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val entry = ViewEntry(ViewEntry.BROKEN, message = "viewer registry: ${e.message}")
            return refs.associate { it.key to entry }
        }
        return refs.associate { it.key to resolveOne(it, viewers, documentDir) }
    }

    private suspend fun resolveOne(
        ref: ViewRef,
        viewers: List<ViewerStatus>,
        documentDir: String?
    ): ViewEntry {
        val data = try {
            ref.data?.let { loadData(it, documentDir) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return ViewEntry(ViewEntry.INVALID, message = "data ${ref.data}: ${e.message}")
        }
        val viewer = viewers.firstOrNull { it.name == ref.name }
            ?: return ViewEntry(
                ViewEntry.MISSING,
                data = data,
                message = "viewer '${ref.name}' is not registered"
            )
        if (viewer.status != ViewerStatus.Status.OK) {
            return ViewEntry(
                ViewEntry.BROKEN,
                data = data,
                message = "viewer source ${viewer.source} is missing"
            )
        }
        return try {
            ViewEntry(ViewEntry.OK, html = entryHtml(viewerFolder(ref, viewer)), data = data)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            ViewEntry(ViewEntry.BROKEN, data = data, message = "viewer '${ref.name}': ${e.message}")
        }
    }

    /** 펜스의 `@해시`, 없으면 등록의 pinned 해시가 가리키는 사본. 둘 다 없으면 정본 폴더. */
    private suspend fun viewerFolder(ref: ViewRef, viewer: ViewerStatus): String {
        val pin = ref.pin ?: viewer.pinned?.takeIf { viewer.follow == ViewerStatus.Follow.PINNED }
            ?: return viewer.source
        return "${home().trimEnd('/')}/$CACHE_DIR/$pin/${ref.name}"
    }

    private suspend fun entryHtml(folder: String): String {
        val manifest = Json.parseToJsonElement(files.read("$folder/$MANIFEST")).jsonObject
        val entry = manifest["entry"]?.jsonPrimitive?.content
            ?: throw IllegalStateException("$MANIFEST has no entry")
        return files.read(joinPath(folder, entry))
    }

    private suspend fun loadData(path: String, documentDir: String?): JsonElement {
        val dir = documentDir ?: throw IllegalStateException("document folder is unknown")
        val text = files.read(joinPath(dir, percentDecode(path)))
        return when (dataFormatOf(path)) {
            DataFormat.JSON -> Json.parseToJsonElement(text)
            DataFormat.YAML -> toJson(loadYaml(text))
            else -> throw IllegalStateException("unsupported data file")
        }
    }
}

/** YAML 로더의 값(맵·리스트·스칼라)을 JSON으로. */
internal fun toJson(value: Any?): JsonElement = when (value) {
    null -> JsonNull
    is Map<*, *> -> JsonObject(value.entries.associate { (k, v) -> k.toString() to toJson(v) })
    is List<*> -> JsonArray(value.map(::toJson))
    is Boolean -> JsonPrimitive(value)
    is Number -> JsonPrimitive(value)
    else -> JsonPrimitive(value.toString())
}

private const val CACHE_DIR = "cache"
private const val MANIFEST = "viewer.json"
