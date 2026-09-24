package madang.shared.main

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.FilesApi
import madang.api.client.RunsApi
import madang.api.model.FileEntry
import madang.api.model.FileLens
import madang.api.model.FileTree
import madang.shared.core.CoreApiException
import madang.shared.core.bodyOrThrow

/** 파일 트리에서 처음에 접혀 있는 폴더. 나머지 폴더는 처음에 펼쳐 있다. */
const val MADANG_DIR = ".madang"

/**
 * 파일 트리의 한 줄.
 *
 * @property path 작업 폴더 기준 경로.
 * @property runs 이 폴더를 `cwd`로 선언한 실행 대상. 선언된 것에만 있다.
 * @property change `changed` 렌즈에서 git 상태 코드.
 */
data class FileRow(
    val path: String,
    val depth: Int,
    val dir: Boolean,
    val expanded: Boolean,
    val runs: List<String>,
    val change: String?
) {
    val name: String get() = path.substringAfterLast('/')
}

/**
 * core가 준 평평한 항목을 들여쓴 줄로 바꾼다. 접힌 폴더의 하위는 뺀다.
 *
 * 폴더는 `.madang`만 처음에 접혀 있고, [toggled]에 있는 폴더는 처음과 반대다. 렌즈가 파일만
 * 주면(변경됨·이 페이지) 그 위 폴더를 만들어 넣는다.
 */
fun fileRows(entries: List<FileEntry>, toggled: Set<String>): List<FileRow> {
    val expanded = { path: String -> (path != MADANG_DIR) != (path in toggled) }
    val seen = mutableSetOf<String>()
    val rows = mutableListOf<FileRow>()
    for (entry in entries) {
        for (parent in parentsOf(entry.path)) {
            if (seen.add(parent)) {
                rows +=
                    FileRow(parent, depthOf(parent), true, false, emptyList(), null)
            }
        }
        if (!seen.add(entry.path)) continue
        rows += FileRow(
            path = entry.path,
            depth = depthOf(entry.path),
            dir = entry.type == FileEntry.Type.DIR,
            expanded = false,
            runs = entry.runs.orEmpty(),
            change = entry.change
        )
    }
    return rows
        .filter { row -> parentsOf(row.path).all(expanded) }
        .map { if (it.dir) it.copy(expanded = expanded(it.path)) else it }
}

private fun parentsOf(path: String): List<String> {
    val parts = path.split('/')
    return (1 until parts.size).map { parts.subList(0, it).joinToString("/") }
}

private fun depthOf(path: String): Int = path.count { it == '/' }

/**
 * 파일 탭 상태. [project]가 null이면 닫혀 있다.
 *
 * @property page 열린 페이지. 있으면 그 페이지의 워크트리(있으면)를 훑는다.
 * @property noRepository 변경됨 렌즈인데 git 저장소가 아니다.
 * @property toggled 처음 접힘과 반대로 둔 폴더.
 * @property error 실행 대상 시작이 실패한 이유.
 */
data class FilesState(
    val project: String? = null,
    val page: String? = null,
    val lens: FileLens = FileLens.ALL,
    val tree: Load<FileTree>? = null,
    val noRepository: Boolean = false,
    val toggled: Set<String> = emptySet(),
    val error: String? = null
) {
    val rows: List<FileRow>
        get() = (tree as? Load.Ready)?.value?.let {
            fileRows(it.propertyEntries, toggled)
        }.orEmpty()

    /** 고를 수 있는 렌즈. 이 페이지 렌즈는 페이지가 열려 있을 때만. */
    val lenses: List<FileLens>
        get() = FileLens.entries.filter { it != FileLens.PAGE || page != null }

    /** [row]의 절대 경로. 트리를 받기 전이면 null. */
    fun absolutePath(row: FileRow): String? =
        (tree as? Load.Ready)?.value?.root?.let { it.trimEnd('/') + "/" + row.path }
}

/**
 * 파일 탭. core의 파일 트리(`GET /projects/{p}/files`)를 렌즈로 거른다. 실행 배지는 core가
 * `runs:` 선언에서 붙인 것만 보이고, 배지를 누르면 그 실행 대상을 core가 띄운다. 파일을 여는
 * 일(더블클릭)은 화면이 가운데 열 탭 규칙으로 한다.
 */
class FilesViewModel(
    private val files: FilesApi,
    private val runs: RunsApi,
    private val scope: CoroutineScope
) {
    private val _state = MutableStateFlow(FilesState())
    val state: StateFlow<FilesState> = _state.asStateFlow()

    /** [project]의 트리를 연다. 페이지가 없으면 이 페이지 렌즈는 전체로 돌아간다. */
    fun open(project: String, page: String?) {
        val current = _state.value
        if (current.project == project && current.page == page) return
        val lens = current.lens.takeIf { it != FileLens.PAGE || page != null } ?: FileLens.ALL
        _state.value = FilesState(project = project, page = page, lens = lens)
        reload()
    }

    fun close() {
        _state.value = FilesState(lens = _state.value.lens)
    }

    fun setLens(lens: FileLens) {
        if (lens !in _state.value.lenses) return
        _state.update { it.copy(lens = lens, toggled = emptySet()) }
        reload()
    }

    fun toggle(path: String) = _state.update {
        it.copy(toggled = if (path in it.toggled) it.toggled - path else it.toggled + path)
    }

    /** 트리를 다시 받는다. 받는 동안 앞의 트리를 그대로 보인다. */
    fun reload() {
        val current = _state.value
        val project = current.project ?: return
        _state.update { it.copy(tree = it.tree.takeIf { t -> t is Load.Ready } ?: Load.Loading) }
        scope.launch {
            val (tree, noRepository) = try {
                val tree = files.listFiles(project, current.lens, current.page).bodyOrThrow()
                Load.Ready(tree) to false
            } catch (e: CancellationException) {
                throw e
            } catch (e: CoreApiException) {
                if (e.error?.error == NO_REPO) null to true else Load.Failed(e.message) to false
            } catch (e: Exception) {
                Load.Failed(e.message ?: e::class.simpleName) to false
            }
            _state.update {
                if (it.project == project && it.page == current.page && it.lens == current.lens) {
                    it.copy(tree = tree, noRepository = noRepository)
                } else {
                    it
                }
            }
        }
    }

    /** `runs:`에 선언된 실행 대상을 core가 띄운다. 준비되면 core가 `runs.opened`를 보낸다. */
    fun startRun(name: String) {
        val project = _state.value.project ?: return
        _state.update { it.copy(error = null) }
        scope.launch {
            val started = loadOf { runs.startRunTarget(project, name).bodyOrThrow() }
            if (started is Load.Failed) {
                _state.update {
                    if (it.project ==
                        project
                    ) {
                        it.copy(error = started.message)
                    } else {
                        it
                    }
                }
            }
        }
    }

    /** 작업 트리가 바뀌었다(`git.changed`, run 끝남). 보고 있는 프로젝트면 다시 받는다. */
    fun onChanged(project: String) {
        if (_state.value.project == project) reload()
    }

    private companion object {
        const val NO_REPO = "no_repo"
    }
}
