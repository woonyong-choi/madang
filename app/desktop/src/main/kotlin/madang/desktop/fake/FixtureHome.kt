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
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import madang.api.model.Block
import madang.api.model.BlockContent
import madang.api.model.BlockHeader
import madang.api.model.BlockType
import madang.api.model.DecisionAnswer
import madang.api.model.FileLens
import madang.api.model.FileTree
import madang.api.model.FlowWaitingData
import madang.api.model.GitBranches
import madang.api.model.GitCommitCreate
import madang.api.model.GitDiff
import madang.api.model.GitLogEntry
import madang.api.model.GitStage
import madang.api.model.GitStatus
import madang.api.model.GitWorktree
import madang.api.model.InputParts
import madang.api.model.InputPreview
import madang.api.model.Issue
import madang.api.model.Memory
import madang.api.model.MemoryContent
import madang.api.model.MemoryFile
import madang.api.model.MemoryLayer
import madang.api.model.MessageAccepted
import madang.api.model.MessageCreate
import madang.api.model.MessageRole
import madang.api.model.ObservedPort
import madang.api.model.PageCard
import madang.api.model.PageCreate
import madang.api.model.PageDetail
import madang.api.model.PageStatus
import madang.api.model.PageUpdate
import madang.api.model.PendingDecision
import madang.api.model.PortDeclare
import madang.api.model.Project
import madang.api.model.ProjectCreate
import madang.api.model.ProjectSort
import madang.api.model.ProjectUpdate
import madang.api.model.Question
import madang.api.model.RepoCommitResult
import madang.api.model.RunInput
import madang.api.model.RunRecord
import madang.api.model.RunRef
import madang.api.model.RunResultStatus
import madang.api.model.RunTargetStatus
import madang.api.model.RunTrigger
import madang.api.model.RunUsage
import madang.api.model.RunVerify
import madang.api.model.TrashEntry
import madang.api.model.TrashRestore
import madang.api.model.UndoResult
import madang.api.model.UnknownFile
import madang.api.model.UnknownFileAction
import madang.api.model.Usage
import madang.api.model.ValidationFailure
import madang.shared.core.CoreClient

/** 가짜 core의 응답 하나. [body]가 null이면 본문이 없다. */
data class FixtureResponse(val status: Int, val body: String?)

/**
 * 폴더에 담긴 픽스처로 프로젝트·페이지·블록 경로에 답한다.
 *
 * 폴더 구성: `projects.json`(등록한 Project 배열), `pages/<id>.json`(PageDetail),
 * `blocks/<페이지 id>/<블록 id>.<확장자>`(doc·data 내용), 선택 `events.jsonl`(연결되면 보낼 이벤트),
 * 선택 `git/<프로젝트 id>.diff`(그 프로젝트의 작업 트리 diff, [FixtureGit]), 선택 `files/`·`ports.json`·
 * `usage.json`(사이드바의 파일·포트·사용량, [FixtureSidebar]).
 * 카드와 프로젝트의 페이지 수는 페이지에서 계산한다. 바꾸는 요청은 메모리에만 반영하고 이벤트를 낸다.
 * 블록 원문 저장은 `.json` 블록이면 JSON 문법을 검사한다.
 *
 * 메시지를 받으면 run 하나를 흉내 낸다. [runStep]마다 `run.*` 이벤트를 내고, 끝나면 router·agent
 * 메시지와 run 기록을 붙이고 미등록 파일 하나를 남긴 뒤 정책 단계로 게시한다(`publish.done`).
 * 문장에 "결정"이 있으면 도중에 `flow.waiting`으로 사람 결정을 묻고, 답을 받으면 마저 끝낸다.
 * 문장에 "정책"이 있으면 정책이 게시를 멈추고 묻는 블록(`ask.created`)을 남긴다. 되돌리기는 그
 * run의 게시를 되감는다.
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
    private val git = FixtureGit(dir)
    private val sidebar = FixtureSidebar(dir)
    private val blockEdits = mutableMapOf<Pair<String, String>, String>()
    private val waitingRuns = mutableMapOf<String, FixtureRun>()
    private val published = mutableMapOf<Pair<String, Int>, Int>()
    private val undone = mutableSetOf<Pair<String, Int>>()
    private var publishCount = 0
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

            parts.size == 5 && parts[0] == "pages" && parts[2] == "asks" &&
                parts[4] == "answer" && method == "POST" -> answerAsk(parts[1], parts[3], body)

            parts.size == 5 && parts[0] == "pages" && parts[2] == "runs" && parts[4] == "undo" &&
                method == "POST" -> undoRun(parts[1], parts[3].toIntOrNull())

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

            parts.size == 4 && parts[0] == "pages" && parts[2] == "blocks" && method == "PUT" ->
                replaceBlock(parts[1], parts[3], body)

            parts.size == 4 && parts[0] == "projects" && parts[2] == "git" ->
                gitRequest(method, parts[1], parts[3], body, query)

            parts == listOf("usage") && method == "GET" ->
                sidebar.usage()?.let { ok(json.encodeToString(Usage.serializer(), it)) }

            parts.size == 3 && parts[0] == "projects" && parts[2] == "files" && method == "GET" ->
                filesRequest(parts[1], query)

            parts.size == 3 && parts[0] == "projects" && parts[2] == "ports" && method == "GET" ->
                ok(json.encodeToString(portsSerializer, sidebar.ports(parts[1])))

            parts.size == 5 && parts[0] == "projects" && parts[2] == "ports" &&
                parts[4] == "declare" && method == "POST" ->
                declarePort(parts[1], parts[3].toIntOrNull(), body)

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
        } else if (pageId to blockId in blockEdits) {
            blockEdits.getValue(pageId to blockId)
        } else {
            File(dir, "blocks/$pageId").listFiles { f -> f.nameWithoutExtension == blockId }
                ?.firstOrNull()?.readText().orEmpty()
        }
        return ok(json.encodeToString(Block.serializer(), Block(header, content)))
    }

    /** 블록 원문을 바꾼다. `.json` 블록은 JSON으로 읽히지 않으면 400으로 거부한다. */
    private fun replaceBlock(pageId: String, blockId: String, body: String?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        val header =
            page.blocks.firstOrNull { it.id == blockId } ?: return notFound("block $blockId")
        val content = decode(body, BlockContent.serializer()).content
        if (header.file?.endsWith(".json") == true) {
            jsonIssue(content)?.let { issue ->
                val failure = ValidationFailure(
                    error = ValidationFailure.Error.INVALID,
                    message = "block content failed validation",
                    issues = listOf(issue)
                )
                return FixtureResponse(
                    400,
                    json.encodeToString(ValidationFailure.serializer(), failure)
                )
            }
        }
        blockEdits[pageId to blockId] = content
        emitBlock(page, blockId, type = "block.updated")
        return ok(json.encodeToString(Block.serializer(), Block(header, content)))
    }

    /** JSON 문법 오류. 파서가 알려 준 위치를 줄 번호로 바꾼다. 문제가 없으면 null. */
    private fun jsonIssue(content: String): Issue? {
        val error = runCatching { json.parseToJsonElement(content) }.exceptionOrNull()
            ?: return null
        val offset = JSON_OFFSET.find(error.message.orEmpty())?.groupValues?.get(1)?.toIntOrNull()
        val line = offset?.let { content.take(it).count { c -> c == '\n' } + 1 }
        return Issue(
            code = "invalid-json",
            message = error.message.orEmpty().lineSequence().first(),
            line = line
        )
    }

    private fun gitRequest(
        method: String,
        projectId: String,
        action: String,
        body: String?,
        query: Map<String, String>
    ): FixtureResponse? {
        val project = projects.firstOrNull { it.id == projectId }
            ?: return notFound("project $projectId")
        if (method == "POST") return gitAction(project, action, body)
        if (action == "status") {
            return ok(json.encodeToString(GitStatus.serializer(), git.status(project)))
        }
        if (!git.isRepository(projectId)) {
            return error(409, "no_repo", "$projectId is not a git repository")
        }
        return when (action) {
            "diff" -> ok(
                json.encodeToString(GitDiff.serializer(), GitDiff(git.diff(projectId).orEmpty()))
            )

            "branches" -> ok(json.encodeToString(GitBranches.serializer(), git.branches(projectId)))

            "worktrees" -> ok(
                json.encodeToString(
                    ListSerializer(GitWorktree.serializer()),
                    git.worktrees(project)
                )
            )

            "log" -> ok(
                json.encodeToString(
                    ListSerializer(GitLogEntry.serializer()),
                    git.log(projectId, query["limit"]?.toIntOrNull() ?: GIT_LOG_DEFAULT)
                )
            )

            else -> null
        }
    }

    /** 스테이지·커밋·푸시·풀·git 시작을 메모리에 반영하고 `git.changed`를 낸다. */
    private fun gitAction(project: Project, action: String, body: String?): FixtureResponse? {
        if (action == "init") {
            if (!git.init(project.id)) return error(409, "conflict", "already a repository")
            emitGitChanged(project, action)
            return FixtureResponse(
                201,
                json.encodeToString(GitStatus.serializer(), git.status(project))
            )
        }
        if (!git.isRepository(project.id)) {
            return error(409, "no_repo", "${project.id} is not a git repository")
        }
        val response = when (action) {
            "stage" -> {
                git.stage(project, decode(body, GitStage.serializer()).paths)
                ok(json.encodeToString(GitStatus.serializer(), git.status(project)))
            }

            "commit" -> {
                val hash = git.commit(project, decode(body, GitCommitCreate.serializer()).message)
                    ?: return error(409, "conflict", "nothing is staged")
                ok(json.encodeToString(RepoCommitResult.serializer(), RepoCommitResult(hash)))
            }

            "pull" -> ok(json.encodeToString(GitStatus.serializer(), git.status(project)))

            "push" -> return error(409, "conflict", "no remote named origin")

            else -> return null
        }
        emitGitChanged(project, action)
        return response
    }

    private fun emitGitChanged(project: Project, action: String) = emit(
        "git.changed",
        project.id,
        null,
        buildJsonObject {
            put("folder", project.path)
            put("action", action)
        }
    )

    /** 파일 트리. 변경됨 렌즈인데 저장소가 아니면 409 `no_repo`. */
    private fun filesRequest(projectId: String, query: Map<String, String>): FixtureResponse {
        val project = projects.firstOrNull { it.id == projectId }
            ?: return notFound("project $projectId")
        val lens = query["lens"]?.let(FileLens::decode) ?: FileLens.ALL
        val page = query["page"]?.takeIf { it.isNotEmpty() }
        if (lens == FileLens.PAGE &&
            page == null
        ) {
            return error(400, "invalid", "lens=page needs page")
        }
        val tree = sidebar.files(project, lens, page, git.status(project))
            ?: return error(409, "no_repo", "$projectId is not a git repository")
        return ok(json.encodeToString(FileTree.serializer(), tree))
    }

    /** 관찰한 포트를 선언으로 저장하고 `ports.changed`를 낸다. */
    private fun declarePort(projectId: String, port: Int?, body: String?): FixtureResponse {
        val name = decode(body, PortDeclare.serializer()).name
        val observed = port?.let { sidebar.declare(projectId, it, name) }
            ?: return notFound("port $port")
        emit(
            "ports.changed",
            projectId,
            null,
            buildJsonObject {
                put("name", name)
                put("ports", json.encodeToJsonElement(portsSerializer, sidebar.ports(projectId)))
            }
        )
        val target = RunTargetStatus(
            name = name,
            command = observed.command.orEmpty(),
            cwd = observed.cwd ?: ".",
            running = false,
            ports = listOf(observed),
            opens = "http://localhost:${observed.port}"
        )
        return FixtureResponse(201, json.encodeToString(RunTargetStatus.serializer(), target))
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
                        prompt = "ledger.md 보정에 실패했습니다. 어떻게 할까요?",
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
            changedFiles = listOf("ledger.md"),
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
        if (POLICY_WORD in run.text) refuse(run) else publish(run)
    }

    /** 정책 단계가 run의 문서를 게시한다. */
    private fun publish(run: FixtureRun) {
        val page = pages[run.page] ?: return
        val n = ++publishCount
        published[run.page to run.n] = n
        emit("publish.done", page.project, page.id, publishData(n, undo = false), run.n)
    }

    /** 정책이 게시를 멈추고 묻는 블록을 남긴다. 답을 기다린다. */
    private fun refuse(run: FixtureRun) {
        val page = pages[run.page] ?: return
        val ask = BlockHeader(
            id = nextBlockId(page),
            type = BlockType.MESSAGE,
            role = MessageRole.ROUTER,
            ts = now(),
            run = run.n,
            text = "$POLICY_PROMPT\n\n- $POLICY_REASON\n\n선택지: ${POLICY_OPTIONS.joinToString(
                " | "
            )}"
        )
        val decision = PendingDecision(
            id = "q${run.n}",
            run = run.n,
            question = Question(Question.Kind.CHOICE, POLICY_PROMPT, options = POLICY_OPTIONS),
            ask = ask.id,
            reasons = listOf(POLICY_REASON)
        )
        val waiting = FlowWaitingData(decision = decision)
        val asking = page.copy(blocks = page.blocks + ask, waiting = waiting, updated = now())
        pages[page.id] = asking
        waitingRuns[page.id] = run
        emitBlock(asking, ask.id, run.n)
        emit(
            "flow.waiting",
            page.project,
            page.id,
            json.encodeToJsonElement(FlowWaitingData.serializer(), waiting),
            run.n
        )
        val created = buildJsonObject {
            put("block", ask.id)
            put("decision", decision.id)
            put("prompt", POLICY_PROMPT)
            put("reasons", json.encodeToJsonElement(stringsSerializer, listOf(POLICY_REASON)))
            put("options", json.encodeToJsonElement(stringsSerializer, POLICY_OPTIONS))
        }
        emit("ask.created", page.project, page.id, created, run.n, block = ask.id)
    }

    /**
     * 묻는 블록에 답한다. 답은 블록으로 남는다. merge면 게시하고, retry면 같은 요청을 정책 거부
     * 없이 다시 돌리고, stop이면 멈춘다.
     */
    private fun answerAsk(pageId: String, ask: String, body: String?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        val decision = page.waiting?.decision?.takeIf { it.ask == ask }
            ?: return notFound("flow waiting on $ask")
        val choice = decode(body, DecisionAnswer.serializer()).choice
        if (choice !in decision.question.options.orEmpty()) {
            return error(400, "invalid", "choice $choice is not an option")
        }
        val answer = BlockHeader(
            id = nextBlockId(page),
            type = BlockType.MESSAGE,
            role = MessageRole.USER,
            ts = now(),
            text = choice
        )
        val answered = page.copy(blocks = page.blocks + answer, waiting = null, updated = now())
        pages[pageId] = answered
        emitBlock(answered, answer.id)
        val run = waitingRuns.remove(pageId)
        when {
            run == null || choice == STOP -> emitPage("page.updated", answered)

            choice == RETRY -> runScope.launch {
                val again = run.copy(
                    n = answered.runs.size + 1,
                    text = run.text.replace(POLICY_WORD, "")
                )
                play(again)
            }

            else -> runScope.launch {
                delay(runStep)
                synchronized(lock) {
                    publish(run)
                    pages[pageId]?.let { emitPage("page.updated", it) }
                }
            }
        }
        return FixtureResponse(202, null)
    }

    /** run 하나를 되돌린다: 그 run의 게시를 되감고 페이지 파일을 되돌린 것으로 답한다. */
    private fun undoRun(pageId: String, n: Int?): FixtureResponse {
        val page = pages[pageId] ?: return notFound("page $pageId")
        if (n == null || page.runs.none { it.n == n }) return notFound("run $n")
        if (!undone.add(pageId to n)) return error(409, "nothing-to-undo", "run $n is undone")
        val unpublished = listOfNotNull(published.remove(pageId to n))
        unpublished.forEach {
            emit("publish.done", page.project, pageId, publishData(it, undo = true), n)
        }
        emitPage("page.updated", page)
        val result = UndoResult(
            run = n,
            restored = listOf("ledger.md", "page.md"),
            skipped = emptyList(),
            reverted = emptyList(),
            unpublished = unpublished
        )
        return ok(json.encodeToString(UndoResult.serializer(), result))
    }

    private fun publishData(n: Int, undo: Boolean) = buildJsonObject {
        put("n", n)
        put("undo", undo)
    }

    private fun preview(page: PageDetail, text: String?): InputPreview {
        val route = routeFor(text.orEmpty())
        val memory = memoryOf(page)
        val parts = InputParts(
            systemEst = SYSTEM_TOKENS,
            profile = memory.profile.tokens,
            brief = memory.brief.tokens,
            ledger = memory.ledger.tokens,
            contract = CONTRACT_TOKENS,
            target = 0,
            request = FixtureMemory.tokens(text.orEmpty())
        )
        val total = parts.systemEst + parts.profile + parts.brief + parts.ledger + parts.contract +
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
        return Memory(memory.profile(), memory.brief(project), memory.ledger(page, project))
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
            MemoryLayer.PROFILE -> memoryOf(page).profile
            MemoryLayer.BRIEF -> memoryOf(page).brief
            MemoryLayer.LEDGER -> memoryOf(page).ledger
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

    private fun emitBlock(
        page: PageDetail,
        blockId: String,
        run: Int? = null,
        type: String = "block.added"
    ) {
        val header = page.blocks.first { it.id == blockId }
        emit(
            type,
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
        const val GIT_LOG_DEFAULT = 50
        val portsSerializer = ListSerializer(ObservedPort.serializer())
        val stringsSerializer = ListSerializer(String.serializer())
        const val DECISION_WORD = "결정"
        const val POLICY_WORD = "정책"
        const val POLICY_PROMPT = "정책이 게시를 멈췄습니다. 어떻게 할까요?"
        const val POLICY_REASON = "테스트 실패(종료 코드 1)"
        const val RETRY = "retry"
        const val STOP = "stop"
        val POLICY_OPTIONS = listOf("merge", RETRY, STOP)
        const val SYSTEM_TOKENS = 24600
        const val CONTRACT_TOKENS = 420
        const val OUTPUT_TOKENS = 640

        val JSON_OFFSET = Regex("""at offset (\d+)""")

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
