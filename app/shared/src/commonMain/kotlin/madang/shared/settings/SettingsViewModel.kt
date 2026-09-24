package madang.shared.settings

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.ProjectsApi
import madang.api.model.ConfigDocument
import madang.api.model.Issue
import madang.api.model.Project
import madang.api.model.RoutesDocument
import madang.api.model.RunnerStatus
import madang.shared.core.CoreApiException
import madang.shared.core.CoreClient
import madang.shared.core.bodyOrThrow

/** 설정 파일(yaml) 편집기 상태. */
sealed interface DocumentStatus {
    data object Loading : DocumentStatus

    data object Editing : DocumentStatus

    data object Saving : DocumentStatus

    data object Saved : DocumentStatus

    /** core 검사기가 거부했다. */
    data class Invalid(val issues: List<Issue>) : DocumentStatus

    data class Error(val message: String) : DocumentStatus
}

/** 설정 화면에서 원문으로 고치는 yaml 파일. */
enum class SettingsDocument {
    /** 앱 홈 `config.yaml`. */
    CONFIG,

    /** 고른 프로젝트의 `.madang/config.yaml`. */
    PROJECT_CONFIG,

    /** 라우팅 표 `routes.yaml`. */
    ROUTES
}

/** yaml 원문 하나와 그 편집 상태. */
data class DocumentEditor(
    val text: String = "",
    val status: DocumentStatus = DocumentStatus.Loading
) {
    val issues: List<Issue> get() = (status as? DocumentStatus.Invalid)?.issues.orEmpty()

    /** 줄 번호(1부터)별 검사 문제. */
    val issuesByLine: Map<Int, List<Issue>>
        get() = issues.filter { it.line != null }.groupBy { checkNotNull(it.line) }

    val canSave: Boolean
        get() = status == DocumentStatus.Editing || status is DocumentStatus.Invalid
}

data class SettingsState(
    val coreUrl: String = "",
    val coreBinary: String = "",
    val connectedUrl: String = "",
    val language: Language = Language.KO,
    val notifications: Boolean = true,
    val documents: Map<SettingsDocument, DocumentEditor> =
        SettingsDocument.entries.associateWith { DocumentEditor() },
    val projects: List<Project> = emptyList(),
    val project: String? = null,
    val runners: List<RunnerStatus> = emptyList(),
    val runnersError: String? = null
) {
    fun document(document: SettingsDocument): DocumentEditor = documents.getValue(document)
}

/**
 * 설정 화면. core 주소, 앱 설정·프로젝트 설정(config.yaml), routes.yaml, 실행기 목록, 언어.
 *
 * core 주소와 실행 파일 경로는 앱 설정에 저장하고 [onReconnect]로 다시 연결한다.
 * yaml 파일은 앱이 직접 읽거나 쓰지 않고 core에 원문을 보내 검사 결과를 받는다.
 *
 * @param project 처음 고를 프로젝트. 없으면 등록한 첫 프로젝트.
 */
class SettingsViewModel(
    private val core: CoreClient,
    private val store: AppSettingsStore,
    private val scope: CoroutineScope,
    private val onLanguageChange: (Language) -> Unit,
    private val onReconnect: () -> Unit,
    project: String? = null
) {
    private val _state = MutableStateFlow(initialState(project))
    val state: StateFlow<SettingsState> = _state.asStateFlow()

    private val projectsApi = core.api(::ProjectsApi)

    init {
        reload(SettingsDocument.CONFIG)
        reload(SettingsDocument.ROUTES)
        loadProjects()
        refreshRunners()
    }

    fun setCoreUrl(url: String) = _state.update { it.copy(coreUrl = url) }

    fun setCoreBinary(path: String) = _state.update { it.copy(coreBinary = path) }

    /** 연결 설정을 저장하고 새 설정으로 core를 다시 찾는다. */
    fun applyConnection() {
        val current = _state.value
        store.save(
            store.load().copy(
                coreUrl = current.coreUrl.trim().ifEmpty { null },
                coreBinary = current.coreBinary.trim().ifEmpty { null }
            )
        )
        onReconnect()
    }

    /** run 완료·실패와 묻는 블록의 시스템 알림을 켜거나 끈다. */
    fun setNotifications(enabled: Boolean) {
        store.save(store.load().copy(notifications = enabled))
        _state.update { it.copy(notifications = enabled) }
    }

    fun setLanguage(language: Language) {
        store.save(store.load().copy(language = language))
        _state.update { it.copy(language = language) }
        onLanguageChange(language)
    }

    fun setText(document: SettingsDocument, text: String) =
        setDocument(document) { DocumentEditor(text, DocumentStatus.Editing) }

    /** 프로젝트 설정 편집기를 [project]의 파일로 바꾼다. */
    fun selectProject(project: String) {
        if (_state.value.project == project) return
        _state.update { it.copy(project = project) }
        reload(SettingsDocument.PROJECT_CONFIG)
    }

    /** [document]를 core에 보낸다. 검사에 걸리면 원문을 그대로 두고 문제를 보인다. */
    fun save(document: SettingsDocument) {
        val text = _state.value.document(document).text
        val project = _state.value.project
        setDocument(document) { it.copy(status = DocumentStatus.Saving) }
        scope.launch {
            var saved: String? = null
            val status = attempt {
                saved = send(document, project, text)
                DocumentStatus.Saved
            }
            if (isStale(document, project)) return@launch
            setDocument(document) { DocumentEditor(saved ?: it.text, status) }
        }
    }

    /** [document]를 core에서 다시 받는다. 고치던 원문은 버린다. */
    fun reload(document: SettingsDocument) {
        val project = _state.value.project
        if (document == SettingsDocument.PROJECT_CONFIG && project == null) return
        setDocument(document) { it.copy(status = DocumentStatus.Loading) }
        scope.launch {
            var text: String? = null
            val status = attempt {
                text = fetch(document, project)
                DocumentStatus.Editing
            }
            if (isStale(document, project)) return@launch
            setDocument(document) { DocumentEditor(text ?: it.text, status) }
        }
    }

    fun refreshRunners() {
        scope.launch {
            try {
                val runners = core.runners.listRunners().bodyOrThrow().runners
                _state.update { it.copy(runners = runners, runnersError = null) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(runnersError = e.message ?: "error") }
            }
        }
    }

    /** 등록한 프로젝트를 받고, 고른 프로젝트가 없거나 사라졌으면 첫 프로젝트를 고른다. */
    private fun loadProjects() {
        scope.launch {
            val projects = try {
                projectsApi.listProjects().bodyOrThrow()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                val status = DocumentStatus.Error(e.message ?: "error")
                setDocument(SettingsDocument.PROJECT_CONFIG) { it.copy(status = status) }
                return@launch
            }
            val chosen = _state.value.project?.takeIf { id -> projects.any { it.id == id } }
                ?: projects.firstOrNull()?.id
            _state.update { it.copy(projects = projects, project = chosen) }
            reload(SettingsDocument.PROJECT_CONFIG)
        }
    }

    private suspend fun fetch(document: SettingsDocument, project: String?): String =
        when (document) {
            SettingsDocument.CONFIG -> core.setup.getConfig().bodyOrThrow().text

            SettingsDocument.PROJECT_CONFIG ->
                core.setup.getProjectConfig(checkNotNull(project)).bodyOrThrow().text

            SettingsDocument.ROUTES -> core.setup.getRoutes().bodyOrThrow().text
        }

    private suspend fun send(document: SettingsDocument, project: String?, text: String): String =
        when (document) {
            SettingsDocument.CONFIG -> core.setup.saveConfig(
                ConfigDocument(text)
            ).bodyOrThrow().text

            SettingsDocument.PROJECT_CONFIG ->
                core.setup
                    .saveProjectConfig(
                        checkNotNull(project),
                        ConfigDocument(text)
                    ).bodyOrThrow().text

            SettingsDocument.ROUTES ->
                core.setup.saveRoutes(RoutesDocument(text)).bodyOrThrow().text
        }

    /** 그사이 다른 프로젝트를 골랐으면 그 전 프로젝트 설정의 결과는 버린다. */
    private fun isStale(document: SettingsDocument, project: String?): Boolean =
        document == SettingsDocument.PROJECT_CONFIG && _state.value.project != project

    private fun setDocument(
        document: SettingsDocument,
        change: (DocumentEditor) -> DocumentEditor
    ) = _state.update {
        it.copy(documents = it.documents + (document to change(it.document(document))))
    }

    private fun initialState(project: String?): SettingsState {
        val settings = store.load()
        return SettingsState(
            coreUrl = settings.coreUrl.orEmpty(),
            coreBinary = settings.coreBinary.orEmpty(),
            connectedUrl = core.baseUrl,
            language = settings.language,
            notifications = settings.notifications,
            project = project
        )
    }

    /** 검사 실패(400)는 [DocumentStatus.Invalid], 그 밖의 실패는 [DocumentStatus.Error]로 바꾼다. */
    private suspend fun attempt(block: suspend () -> DocumentStatus): DocumentStatus = try {
        block()
    } catch (e: CancellationException) {
        throw e
    } catch (e: CoreApiException) {
        if (e.status == BAD_REQUEST) {
            DocumentStatus.Invalid(e.issues)
        } else {
            DocumentStatus.Error(e.message.orEmpty())
        }
    } catch (e: Exception) {
        DocumentStatus.Error(e.message ?: "error")
    }
}

private const val BAD_REQUEST = 400
