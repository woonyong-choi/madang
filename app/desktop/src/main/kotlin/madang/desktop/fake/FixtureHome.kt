package madang.desktop.fake

import java.io.File
import java.time.OffsetDateTime
import java.time.temporal.ChronoUnit
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import madang.api.model.Block
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.DecisionAnswer
import madang.api.model.FlowWaitingData
import madang.api.model.InputParts
import madang.api.model.InputPreview
import madang.api.model.Memory
import madang.api.model.MemoryContent
import madang.api.model.MemoryFile
import madang.api.model.MemoryLayer
import madang.api.model.MessageAccepted
import madang.api.model.MessageCreate
import madang.api.model.MessageRole
import madang.api.model.PageCard
import madang.api.model.PageCreate
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.PageUpdate
import madang.api.model.PendingDecision
import madang.api.model.Project
import madang.api.model.ProjectCreate
import madang.api.model.ProjectSort
import madang.api.model.ProjectUpdate
import madang.api.model.Question
import madang.api.model.RunInput
import madang.api.model.RunRecord
import madang.api.model.RunRef
import madang.api.model.RunResultStatus
import madang.api.model.RunTrigger
import madang.api.model.RunUsage
import madang.api.model.RunVerify
import madang.api.model.TrashEntry
import madang.api.model.TrashRestore
import madang.api.model.UnknownFile
import madang.api.model.UnknownFileAction
import madang.api.model.ValidationFailure
import madang.shared.core.CoreClient

/** 가짜 core의 응답 하나. [body]가 null이면 본문이 없다. */
data class FixtureResponse(val status: Int, val body: String?)

/**
 * 폴더에 담긴 픽스처로 프로젝트·페이지·블록 경로에 답한다.
 *
 * 폴더 구성: `projects.json`(등록한 Project 배열), `pages/<id>.json`(PageDetail),
 * `blocks/<페이지 id>/<블록 id>.<확장자>`(doc·data 내용), 선택 `events.jsonl`(연결되면 보낼 이벤트).
 * 카드와 프로젝트의 페이지 수는 페이지에서 계산한다. 바꾸는 요청은 메모리에만 반영하고 이벤트를 낸다.
 *
 * 메시지를 받으면 run 하나를 흉내 낸다. [runStep]마다 `run.*` 이벤트를 내고, 끝나면 router·agent
 * 메시지와 run 기록을 붙이고 미등록 파일 하나를 남긴다. 문장에 "결정"이 있으면 도중에
 * `flow.waiting`으로 사람 결정을 묻고, 답을 받으면 마저 끝낸다.
 */
class FixtureHome(private val dir: File, private val runStep: Duration = 600.milliseconds) {

    private val json = CoreClient.CoreJson
    private val lock = Any()
    private val projects = decodeFile(
        File(dir, "projects.json"),
        ListSerializer(Project.serializer())
    )
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

    private val memory = FixtureMemory()
    private val trash = FixtureTrash()
    private val waitingRuns = mutableMapOf<String, FixtureRun>()
    private val runScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val _events = MutableSharedFlow<String>(
        extraBufferCapacity = 64,
        onBufferOverflow = BufferOverflow.DROP_OLDEST
    )

    /** 바꾸는 요청 뒤에 나는 이벤트. */
    val events: SharedFlow<String> = _events

    /** [method] [path] 요청에 답한다. [query]는 쿼리 파라미터. 픽스처가 모르는 경로면 null. */
    fun handle(
        method: String,
        path: String,
        body: String?,
        query: Map<String, String> = emptyMap()
    ): FixtureResponse? = synchronized(lock) {
        val parts = path.trim('/').split('/')
        when {
            parts == listOf("trash") && method == "GET" ->
                ok(json.encodeToString(ListSerializer(TrashEntry.serializer()), trash.entries()))

            parts.size == 3 && parts[0] == "trash" && parts[2] == "restore" && method == "POST" ->
                restore(parts[1])

            parts.size == 3 && parts[0] == "pages" -> pageAction(
                method,
                parts[1],
                parts[2],
                body,
                query
            )

            parts.size == 4 && parts[0] == "pages" && parts[2] == "memory" && method == "PUT" ->
                saveMemory(parts[1], parts[3], body)

            parts.size == 4 && parts[0] == "pages" && parts[2] == "unknown-files" &&
                method == "POST" -> resolveUnknownFile(parts[1], decodeSegment(parts[3]), body)

            parts.size == 5 && parts[0] == "pages" && parts[2] == "decisions" &&
                parts[4] == "answer" && method == "POST" -> answer(parts[1], parts[3], body)

            parts == listOf("projects") && method == "GET" -> ok(projectsJson())

            parts == listOf(
                "projects"
            ) && method == "POST" -> createProject(decode(body, ProjectCreate.serializer()))

            parts.size == 2 && parts[0] == "projects" -> projectRequest(method, parts[1], body)

            parts.size == 3 && parts[0] == "projects" && parts[2] == "pages" ->
                pagesRequest(method, parts[1], body)

            parts.size == 2 && parts[0] == "pages" -> pageRequest(method, parts[1], body)

            parts.size == 4 && parts[0] == "pages" && parts[2] == "blocks" && method == "GET" ->
                blockContent(parts[1], parts[3])

            parts.size == 5 && parts[0] == "pages" && parts[2] == "runs" && parts[4] == "cancel" ->
                cancelRun(parts[1], parts[3].toIntOrNull())

            else -> null
        }
    }

    private fun projectRequest(method: String, id: String, body: String?): FixtureResponse? {
        val index = projects.indexOfFirst { it.id == id }
        if (index < 0) return notFound("project $id")
        return when (method) {
            "PATCH" -> {
                val update = decode(body, ProjectUpdate.serializer())
                val old = projects[index]
                projects[index] = old.copy(
                    title = update.title ?: old.title,
                    parent = update.parent ?: old.parent,
                    icon = update.icon ?: old.icon,
                    color = update.color ?: old.color,
                    sort = update.sort ?: old.sort
                )
                val project = withCounts(projects[index])
                emitProject("project.updated", project)
                ok(json.encodeToString(Project.serializer(), project))
            }

            "DELETE" -> {
                if (projects.any { it.parent == id }) {
                    return error(409, "conflict", "project $id still has child projects")
                }
                projects.removeAt(index)
                pages.values.removeAll { it.project == id }
                emit("project.deleted", id, null, buildJsonObject { put("id", id) })
                FixtureResponse(204, null)
            }

            else -> null
        }
    }

    /** 폴더를 프로젝트로 등록한다. id를 생략하면 폴더 이름에서 만들고 겹치면 번호를 붙인다. */
    private fun createProject(request: ProjectCreate): FixtureResponse {
        val path = request.path.trimEnd('/')
        if (projects.any { it.path == path }) return error(409, "conflict", "$path is registered")
        val name = path.substringAfterLast('/')
        val base = request.id ?: name.lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-')
            .ifEmpty { "project" }
        val id = generateSequence(1) { it + 1 }
            .map { if (it == 1) base else "$base-$it" }
            .first { candidate -> projects.none { it.id == candidate } }
        val project = Project(
            id = id,
            title = request.title ?: name,
            path = path,
            parent = request.parent,
            icon = request.icon,
            color = request.color,
            sort = request.sort ?: ProjectSort.UPDATED
        )
        projects += project
        emitProject("project.created", withCounts(project))
        return FixtureResponse(201, json.encodeToString(Project.serializer(), withCounts(project)))
    }

    private fun pagesRequest(method: String, id: String, body: String?): FixtureResponse? {
        val project = projects.firstOrNull { it.id == id } ?: return notFound("project $id")
        return when (method) {
            "GET" -> ok(
                json.encodeToString(ListSerializer(PageCard.serializer()), cardsIn(project))
            )

            "POST" -> createPage(id, decode(body, PageCreate.serializer()))

            else -> null
        }
    }

    private fun createPage(project: String, request: PageCreate): FixtureResponse {
        val now = now()
        val id = generateSequence(1) { it + 1 }
            .map { "${now.take(10)}-page-$it" }
            .first { it !in pages }
        val page = PageDetail(
            id = id,
            project = project,
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
                if (update.project != null && projects.none { it.id == update.project }) {
                    return notFound("project ${update.project}")
                }
                val changed = page.copy(
                    title = update.title ?: page.title,
                    pinned = update.pinned ?: page.pinned,
                    tags = update.tags ?: page.tags,
                    project = update.project ?: page.project,
                    updated = now()
                )
                pages[id] = changed
                emitPage("page.updated", changed)
                ok(json.encodeToString(PageCard.serializer(), changed.toCard()))
            }

            "DELETE" -> {
                pages.remove(id)
                trash.add(page, now())
                emit("page.deleted", page.project, id, buildJsonObject { put("id", id) })
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
        emit("run.failed", page.project, pageId, data, run)
        return FixtureResponse(202, null)
    }

    private fun pageAction(
        method: String,
        id: String,
        action: String,
        body: String?,
        query: Map<String, String>
    ): FixtureResponse? {
        val page = pages[id] ?: return notFound("page $id")
        return when {
            action == "messages" && method == "POST" ->
                sendMessage(page, decode(body, MessageCreate.serializer()).text)

            action == "preview-input" && method == "GET" ->
                ok(json.encodeToString(InputPreview.serializer(), preview(page, query["text"])))

            action == "memory" && method == "GET" -> ok(
                json.encodeToString(Memory.serializer(), memoryOf(page))
            )

            action == "unknown-files" && method == "GET" -> ok(unknownFilesJson(page))

            else -> null
        }
    }

    /** 사용자 메시지를 붙이고 run을 흉내 내기 시작한다. */
    private fun sendMessage(page: PageDetail, text: String): FixtureResponse {
        if (page.waiting != null) return error(409, "conflict", "page is waiting for a decision")
        val message = BlockHeader(
            id = nextBlockId(page),
            type = BlockType.MESSAGE,
            role = MessageRole.USER,
            ts = now(),
            text = text
        )
        val changed = page.copy(blocks = page.blocks + message, updated = now())
        pages[page.id] = changed
        emitBlock(changed, message.id)
        val run = FixtureRun(page.id, page.runs.size + 1, message.id, text)
        runScope.launch { play(run) }
        val accepted = json.encodeToString(
            MessageAccepted.serializer(),
            MessageAccepted(message.id)
        )
        return FixtureResponse(202, accepted)
    }

    private suspend fun play(run: FixtureRun) {
        val route = routeFor(run.text)
        step(run, "run.started") {
            buildJsonObject {
                put("runner", route.runner)
                put("model", route.model)
                put("kind", route.kind)
                put("tier", 1)
                put("trigger", buildJsonObject { put("message", run.message) })
            }
        }
        step(run, "run.assembled") { page ->
            val input = preview(page, run.text)
            buildJsonObject {
                put("parts", json.encodeToJsonElement(InputParts.serializer(), input.parts))
                put("total_est", input.totalEst)
            }
        }
        step(run, "run.progress") {
            buildJsonObject {
                put("type", "tool_call")
                put("name", "apply_patch")
                put("summary", "blocks/scratch-${run.n}.txt")
            }
        }
        if (DECISION_WORD in run.text) ask(run) else finishAfterStep(run)
    }

    /** [runStep]만큼 기다린 뒤 페이지가 남아 있으면 이벤트 하나를 낸다. */
    private suspend fun step(run: FixtureRun, type: String, data: (PageDetail) -> JsonElement) {
        delay(runStep)
        synchronized(lock) {
            val page = pages[run.page] ?: return
            emit(type, page.project, page.id, data(page), run.n)
        }
    }

    private suspend fun ask(run: FixtureRun) {
        delay(runStep)
        synchronized(lock) {
            val page = pages[run.page] ?: return
            val waiting = FlowWaitingData(
                decision = PendingDecision(
                    id = "q${run.n}",
                    run = run.n,
                    question = Question(
                        kind = Question.Kind.CHOICE,
                        prompt = "state.md 보정에 실패했습니다. 어떻게 할까요?",
                        options = listOf("retry", "next_tier", "stop")
                    )
                )
            )
            pages[page.id] = page.copy(waiting = waiting)
            waitingRuns[page.id] = run
            emit(
                "flow.waiting",
                page.project,
                page.id,
                json.encodeToJsonElement(FlowWaitingData.serializer(), waiting),
                run.n
            )
        }
    }

    private fun answer(pageId: String, decision: String, body: String?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        if (page.waiting?.decision?.id != decision) return error(409, "conflict", "not waiting")
        decode(body, DecisionAnswer.serializer())
        pages[pageId] = page.copy(waiting = null)
        waitingRuns.remove(pageId)?.let { run -> runScope.launch { finishAfterStep(run) } }
        return FixtureResponse(202, null)
    }

    private suspend fun finishAfterStep(run: FixtureRun) {
        delay(runStep)
        synchronized(lock) { finish(run) }
    }

    /** run을 끝낸다: router·agent 메시지, run 기록, 미등록 파일 하나. */
    private fun finish(run: FixtureRun) {
        val page = pages[run.page] ?: return
        val route = routeFor(run.text)
        val input = preview(page, run.text)
        val router = BlockHeader(
            id = nextBlockId(page),
            type = BlockType.MESSAGE,
            role = MessageRole.ROUTER,
            ts = now(),
            run = run.n,
            text = "kind=${route.kind} conf=1.00 → ${route.runner}/${route.model}"
        )
        val agent = router.copy(
            id = nextBlockId(page, offset = 1),
            role = MessageRole.AGENT,
            text = "요청을 반영했습니다. 확인할 파일: blocks/scratch-${run.n}.txt"
        )
        val scratch = "blocks/scratch-${run.n}.txt"
        val record = RunRecord(
            n = run.n,
            started = now(),
            finished = now(),
            trigger = RunTrigger(message = run.message),
            kind = route.kind,
            tier = 1,
            runner = route.runner,
            model = route.model,
            input = RunInput(input.parts, input.totalEst),
            usage = RunUsage(input = input.totalEst, cached = 0, output = OUTPUT_TOKENS),
            changedFiles = listOf("state.md"),
            unknownFiles = listOf(scratch),
            verify = RunVerify(),
            resultStatus = RunResultStatus.REVIEW
        )
        val finished = page.copy(
            blocks = page.blocks + router + agent,
            runs = page.runs + record,
            unknownFiles = page.unknownFiles + UnknownFile(scratch, run.n),
            status = PageStatus.REVIEW,
            updated = now()
        )
        pages[page.id] = finished
        emitBlock(finished, router.id, run.n)
        emitBlock(finished, agent.id, run.n)
        emit(
            "run.finished",
            page.project,
            page.id,
            json.encodeToJsonElement(RunRecord.serializer(), record),
            run.n
        )
        emit(
            "page.unknown_files",
            page.project,
            page.id,
            buildJsonObject {
                put("files", json.parseToJsonElement(unknownFilesJson(finished)))
            },
            run.n
        )
        emitPage("page.updated", finished)
    }

    private fun preview(page: PageDetail, text: String?): InputPreview {
        val route = routeFor(text.orEmpty())
        val memory = memoryOf(page)
        val parts = InputParts(
            systemEst = SYSTEM_TOKENS,
            root = memory.root.tokens,
            project = memory.project.tokens,
            state = memory.state.tokens,
            contract = CONTRACT_TOKENS,
            target = 0,
            request = FixtureMemory.tokens(text.orEmpty())
        )
        val total = parts.systemEst + parts.root + parts.project + parts.state + parts.contract +
            parts.target + parts.request
        return InputPreview(
            kind = route.kind,
            tier = 1,
            runner = route.runner,
            model = route.model,
            parts = parts,
            totalEst = total,
            effort = "high"
        )
    }

    private fun memoryOf(page: PageDetail): Memory {
        val project = projects.first { it.id == page.project }
        return Memory(memory.root(), memory.project(project), memory.state(page, project))
    }

    private fun saveMemory(pageId: String, layerName: String, body: String?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        val layer = MemoryLayer.entries.firstOrNull { it.value == layerName }
            ?: return notFound("layer $layerName")
        val content = decode(body, MemoryContent.serializer()).content
        val issues = memory.save(page, layer, content)
        if (issues.isNotEmpty()) {
            val failure = ValidationFailure(
                error = ValidationFailure.Error.INVALID,
                message = "${layer.value}.md failed validation",
                issues = issues
            )
            return FixtureResponse(
                400,
                json.encodeToString(ValidationFailure.serializer(), failure)
            )
        }
        val saved = when (layer) {
            MemoryLayer.ROOT -> memoryOf(page).root
            MemoryLayer.PROJECT -> memoryOf(page).project
            MemoryLayer.STATE -> memoryOf(page).state
        }
        emit(
            "memory.updated",
            page.project,
            page.id,
            buildJsonObject {
                put("layer", layer.value)
                put("tokens", saved.tokens)
            }
        )
        return ok(json.encodeToString(MemoryFile.serializer(), saved))
    }

    private fun resolveUnknownFile(pageId: String, path: String, body: String?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        if (page.unknownFiles.none { it.path == path }) return notFound("unknown file $path")
        decode(body, UnknownFileAction.serializer())
        val changed = page.copy(unknownFiles = page.unknownFiles.filter { it.path != path })
        pages[pageId] = changed
        return ok(unknownFilesJson(changed))
    }

    private fun restore(id: String): FixtureResponse {
        val page = trash.restore(id) ?: return notFound("trash entry $id")
        if (page.id in pages) return error(409, "conflict", "page ${page.id} exists")
        pages[page.id] = page
        emitPage("page.created", page)
        val restored = TrashRestore(id, listOf(FixtureTrash.pagePath(page)))
        return ok(json.encodeToString(TrashRestore.serializer(), restored))
    }

    private fun unknownFilesJson(page: PageDetail): String =
        json.encodeToString(ListSerializer(UnknownFile.serializer()), page.unknownFiles)

    /** 다음 블록 id. `b07` 꼴이고 [offset]만큼 건너뛴다. */
    private fun nextBlockId(page: PageDetail, offset: Int = 0): String {
        val last = page.blocks.mapNotNull { it.id.removePrefix("b").toIntOrNull() }.maxOrNull() ?: 0
        return "b" + (last + 1 + offset).toString().padStart(2, '0')
    }

    private fun emitBlock(page: PageDetail, blockId: String, run: Int? = null) {
        val header = page.blocks.first { it.id == blockId }
        emit(
            "block.added",
            page.project,
            page.id,
            buildJsonObject {
                put("block", json.encodeToJsonElement(BlockHeader.serializer(), header))
            },
            run,
            block = blockId
        )
    }

    private fun projectsJson(): String =
        json.encodeToString(ListSerializer(Project.serializer()), projects.map(::withCounts))

    private fun withCounts(project: Project): Project {
        val inProject = pages.values.filter { it.project == project.id }
        return project.copy(
            pages = inProject.size,
            activePages = inProject.count {
                it.status == PageStatus.DOING ||
                    it.status == PageStatus.BLOCKED
            }
        )
    }

    /** 고정 먼저, 그다음 프로젝트의 정렬. */
    private fun cardsIn(project: Project): List<PageCard> {
        val cards = pages.values.filter { it.project == project.id }.map { it.toCard() }
        val order: Comparator<PageCard> = when (project.sort ?: ProjectSort.UPDATED) {
            ProjectSort.UPDATED -> compareByDescending { it.updated.orEmpty() }
            ProjectSort.CREATED -> compareByDescending { it.created.orEmpty() }
            ProjectSort.TITLE -> compareBy { it.title }
        }
        return cards.sortedWith(compareByDescending<PageCard> { it.pinned }.then(order))
    }

    private fun emitProject(type: String, project: Project) = emit(
        type,
        project.id,
        null,
        buildJsonObject { put("project", json.encodeToJsonElement(Project.serializer(), project)) }
    )

    private fun emitPage(type: String, page: PageDetail) = emit(
        type,
        page.project,
        page.id,
        buildJsonObject {
            put("page", json.encodeToJsonElement(PageCard.serializer(), page.toCard()))
        }
    )

    private fun emit(
        type: String,
        project: String,
        page: String?,
        data: JsonElement,
        run: Int? = null,
        block: String? = null
    ) {
        val event = buildJsonObject {
            put("type", type)
            put("ts", now())
            put("project", project)
            page?.let { put("page", it) }
            run?.let { put("run", JsonPrimitive(it)) }
            block?.let { put("block", it) }
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

    /** 흉내 내는 run 하나. [message]는 run을 일으킨 메시지 블록이다. */
    private data class FixtureRun(
        val page: String,
        val n: Int,
        val message: String,
        val text: String
    )

    private data class Route(val kind: String, val runner: String, val model: String)

    private companion object {
        const val DECISION_WORD = "결정"
        const val SYSTEM_TOKENS = 24600
        const val CONTRACT_TOKENS = 420
        const val OUTPUT_TOKENS = 640

        val ROUTES = mapOf(
            "design" to Route("design", "claude", "claude-opus-5-5"),
            "build" to Route("build", "codex", "gpt-6-sol"),
            "small" to Route("small", "codex", "gpt-6-luna"),
            "review" to Route("review", "claude", "claude-opus-5-5"),
            "explore" to Route("explore", "codex", "gpt-6-luna")
        )

        /** `design:` 같은 접두어가 있으면 그 종류, 없으면 build. */
        fun routeFor(text: String): Route = ROUTES[text.substringBefore(':', "").trim().lowercase()]
            ?: checkNotNull(ROUTES["build"])

        fun decodeSegment(segment: String): String =
            java.net.URLDecoder.decode(segment.replace("+", "%2B"), Charsets.UTF_8)
    }
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
        project = project,
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
