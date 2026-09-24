package madang.desktop.fake

import java.io.File
import java.time.OffsetDateTime
import java.time.temporal.ChronoUnit
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import madang.api.model.Block
import madang.api.model.BlockType
import madang.api.model.MessageRole
import madang.api.model.PageCard
import madang.api.model.PageCreate
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.PageUpdate
import madang.api.model.RunRef
import madang.api.model.Space
import madang.api.model.SpaceCreate
import madang.api.model.SpaceSort
import madang.api.model.SpaceUpdate
import madang.shared.core.CoreClient

/** 가짜 core의 응답 하나. [body]가 null이면 본문이 없다. */
data class FixtureResponse(val status: Int, val body: String?)

/**
 * 폴더에 담긴 앱 홈 픽스처로 공간·페이지·블록 경로에 답한다.
 *
 * 폴더 구성: `spaces.json`(Space 배열), `pages/<id>.json`(PageDetail),
 * `blocks/<페이지 id>/<블록 id>.<확장자>`(doc·data 내용), 선택 `events.jsonl`(연결되면 보낼 이벤트).
 * 카드와 공간의 페이지 수는 페이지에서 계산한다. 바꾸는 요청은 메모리에만 반영하고 이벤트를 낸다.
 */
class FixtureHome(private val dir: File) {

    private val json = CoreClient.CoreJson
    private val lock = Any()
    private val spaces = decodeFile(File(dir, "spaces.json"), ListSerializer(Space.serializer()))
        .toMutableList()
    private val pages = (
        File(dir, "pages").listFiles { f ->
            f.extension == "json"
        } ?: emptyArray()
        )
        .sortedBy { it.name }
        .map { decodeFile(it, PageDetail.serializer()) }
        .associateByTo(linkedMapOf()) { it.id }

    /** 연결되면 먼저 보낼 이벤트(JSON 텍스트). */
    val initialEvents: List<String> = File(dir, "events.jsonl").takeIf { it.isFile }
        ?.readLines()?.filter { it.isNotBlank() }.orEmpty()

    private val _events = MutableSharedFlow<String>(
        extraBufferCapacity = 64,
        onBufferOverflow = BufferOverflow.DROP_OLDEST
    )

    /** 바꾸는 요청 뒤에 나는 이벤트. */
    val events: SharedFlow<String> = _events

    /** [method] [path] 요청에 답한다. 픽스처가 모르는 경로면 null. */
    fun handle(method: String, path: String, body: String?): FixtureResponse? = synchronized(lock) {
        val parts = path.trim('/').split('/')
        when {
            parts == listOf("spaces") && method == "GET" -> ok(spacesJson())

            parts == listOf(
                "spaces"
            ) && method == "POST" -> createSpace(decode(body, SpaceCreate.serializer()))

            parts.size == 2 && parts[0] == "spaces" -> spaceRequest(method, parts[1], body)

            parts.size == 3 && parts[0] == "spaces" && parts[2] == "pages" ->
                pagesRequest(method, parts[1], body)

            parts.size == 2 && parts[0] == "pages" -> pageRequest(method, parts[1], body)

            parts.size == 4 && parts[0] == "pages" && parts[2] == "blocks" && method == "GET" ->
                blockContent(parts[1], parts[3])

            parts.size == 5 && parts[0] == "pages" && parts[2] == "runs" && parts[4] == "cancel" ->
                cancelRun(parts[1], parts[3].toIntOrNull())

            else -> null
        }
    }

    private fun spaceRequest(method: String, slug: String, body: String?): FixtureResponse? {
        val index = spaces.indexOfFirst { it.slug == slug }
        if (index < 0) return notFound("space $slug")
        return when (method) {
            "PATCH" -> {
                val update = decode(body, SpaceUpdate.serializer())
                val old = spaces[index]
                spaces[index] = old.copy(
                    title = update.title ?: old.title,
                    repo = update.repo ?: old.repo,
                    parent = update.parent ?: old.parent,
                    icon = update.icon ?: old.icon,
                    color = update.color ?: old.color,
                    sort = update.sort ?: old.sort
                )
                val space = withCounts(spaces[index])
                emitSpace("space.updated", space)
                ok(json.encodeToString(Space.serializer(), space))
            }

            "DELETE" -> {
                if (pages.values.any { it.space == slug } || spaces.any { it.parent == slug }) {
                    return error(409, "conflict", "space $slug is not empty")
                }
                spaces.removeAt(index)
                emit("space.deleted", slug, null, buildJsonObject { put("id", slug) })
                FixtureResponse(204, null)
            }

            else -> null
        }
    }

    private fun createSpace(request: SpaceCreate): FixtureResponse {
        if (spaces.any { it.slug == request.slug }) return error(409, "conflict", "space exists")
        val space = Space(
            slug = request.slug,
            title = request.title,
            repo = request.repo,
            parent = request.parent,
            icon = request.icon,
            color = request.color,
            sort = request.sort ?: SpaceSort.UPDATED
        )
        spaces += space
        emitSpace("space.created", withCounts(space))
        return FixtureResponse(201, json.encodeToString(Space.serializer(), withCounts(space)))
    }

    private fun pagesRequest(method: String, slug: String, body: String?): FixtureResponse? {
        val space = spaces.firstOrNull { it.slug == slug } ?: return notFound("space $slug")
        return when (method) {
            "GET" -> ok(json.encodeToString(ListSerializer(PageCard.serializer()), cardsIn(space)))
            "POST" -> createPage(slug, decode(body, PageCreate.serializer()))
            else -> null
        }
    }

    private fun createPage(space: String, request: PageCreate): FixtureResponse {
        val now = now()
        val id = generateSequence(1) { it + 1 }
            .map { "${now.take(10)}-page-$it" }
            .first { it !in pages }
        val page = PageDetail(
            id = id,
            space = space,
            title = request.title,
            status = PageStatus.PLANNING,
            pinned = false,
            tags = emptyList(),
            blocks = emptyList(),
            runs = emptyList(),
            unknownFiles = emptyList(),
            kind = request.kind ?: "build",
            created = now,
            updated = now,
            overview = ""
        )
        pages[id] = page
        emitPage("page.created", page)
        return FixtureResponse(201, json.encodeToString(PageDetail.serializer(), page))
    }

    private fun pageRequest(method: String, id: String, body: String?): FixtureResponse? {
        val page = pages[id] ?: return notFound("page $id")
        return when (method) {
            "GET" -> ok(json.encodeToString(PageDetail.serializer(), page))

            "PATCH" -> {
                val update = decode(body, PageUpdate.serializer())
                if (update.space != null && spaces.none { it.slug == update.space }) {
                    return notFound("space ${update.space}")
                }
                val changed = page.copy(
                    title = update.title ?: page.title,
                    pinned = update.pinned ?: page.pinned,
                    tags = update.tags ?: page.tags,
                    space = update.space ?: page.space,
                    updated = now()
                )
                pages[id] = changed
                emitPage("page.updated", changed)
                ok(json.encodeToString(PageCard.serializer(), changed.toCard()))
            }

            "DELETE" -> {
                pages.remove(id)
                emit("page.deleted", page.space, id, buildJsonObject { put("id", id) })
                FixtureResponse(204, null)
            }

            else -> null
        }
    }

    private fun blockContent(pageId: String, blockId: String): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        val header =
            page.blocks.firstOrNull { it.id == blockId } ?: return notFound("block $blockId")
        val content = if (header.type == BlockType.MESSAGE) {
            header.text.orEmpty()
        } else {
            File(dir, "blocks/$pageId").listFiles { f -> f.nameWithoutExtension == blockId }
                ?.firstOrNull()?.readText().orEmpty()
        }
        return ok(json.encodeToString(Block.serializer(), Block(header, content)))
    }

    private fun cancelRun(pageId: String, run: Int?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        val data = buildJsonObject {
            put("result_status", "cancelled")
            put("error", "cancelled")
        }
        emit("run.failed", page.space, pageId, data, run)
        return FixtureResponse(202, null)
    }

    private fun spacesJson(): String =
        json.encodeToString(ListSerializer(Space.serializer()), spaces.map(::withCounts))

    private fun withCounts(space: Space): Space {
        val inSpace = pages.values.filter { it.space == space.slug }
        return space.copy(
            pages = inSpace.size,
            activePages = inSpace.count {
                it.status == PageStatus.DOING ||
                    it.status == PageStatus.BLOCKED
            }
        )
    }

    /** 고정 먼저, 그다음 공간의 정렬. */
    private fun cardsIn(space: Space): List<PageCard> {
        val cards = pages.values.filter { it.space == space.slug }.map { it.toCard() }
        val order: Comparator<PageCard> = when (space.sort ?: SpaceSort.UPDATED) {
            SpaceSort.UPDATED -> compareByDescending { it.updated.orEmpty() }
            SpaceSort.CREATED -> compareByDescending { it.created.orEmpty() }
            SpaceSort.TITLE -> compareBy { it.title }
        }
        return cards.sortedWith(compareByDescending<PageCard> { it.pinned }.then(order))
    }

    private fun emitSpace(type: String, space: Space) = emit(
        type,
        space.slug,
        null,
        buildJsonObject { put("space", json.encodeToJsonElement(Space.serializer(), space)) }
    )

    private fun emitPage(type: String, page: PageDetail) = emit(
        type,
        page.space,
        page.id,
        buildJsonObject {
            put("page", json.encodeToJsonElement(PageCard.serializer(), page.toCard()))
        }
    )

    private fun emit(
        type: String,
        space: String,
        page: String?,
        data: JsonElement,
        run: Int? = null
    ) {
        val event = buildJsonObject {
            put("type", type)
            put("ts", now())
            put("space", space)
            page?.let { put("page", it) }
            run?.let { put("run", JsonPrimitive(it)) }
            put("data", data)
        }
        _events.tryEmit(event.toString())
    }

    private fun ok(body: String) = FixtureResponse(200, body)

    private fun notFound(what: String) = error(404, "not_found", "$what not found")

    private fun error(status: Int, code: String, message: String) = FixtureResponse(
        status,
        JsonObject(
            mapOf("error" to JsonPrimitive(code), "message" to JsonPrimitive(message))
        ).toString()
    )

    private fun <T> decode(body: String?, serializer: KSerializer<T>): T =
        json.decodeFromString(serializer, body ?: "{}")

    private fun <T> decodeFile(file: File, serializer: KSerializer<T>): T =
        json.decodeFromString(serializer, file.readText())

    private fun now(): String = OffsetDateTime.now().truncatedTo(ChronoUnit.SECONDS).toString()
}

/** 페이지로 목록 카드를 만든다. 미리보기는 router가 아닌 마지막 메시지의 첫 줄이다. */
fun PageDetail.toCard(): PageCard {
    val counts = blocks.groupingBy { it.type.value }.eachCount() +
        (if (runs.isNotEmpty()) mapOf(BlockType.RUN.value to runs.size) else emptyMap())
    val lastMessage = blocks.lastOrNull {
        it.type == BlockType.MESSAGE &&
            it.role != MessageRole.ROUTER
    }
    return PageCard(
        id = id,
        space = space,
        title = title,
        status = status,
        pinned = pinned,
        tags = tags,
        blockCounts = counts,
        kind = kind,
        created = created,
        updated = updated,
        preview = lastMessage?.text?.lineSequence()?.firstOrNull(),
        lastRun = runs.lastOrNull()?.let {
            RunRef(
                n = it.n,
                runner = it.runner.orEmpty(),
                model = it.model.orEmpty(),
                resultStatus = it.resultStatus
            )
        },
        firstView = blocks.firstOrNull { it.type == BlockType.VIEW }?.id
    )
}
