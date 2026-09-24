package madang.shared.main

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import madang.api.client.RunsApi
import madang.api.model.ObservedPort
import madang.api.model.PortDeclare
import madang.shared.core.bodyOrThrow

/**
 * 포트 탭 상태. [project]가 null이면 닫혀 있다.
 *
 * @property names "선언으로 저장"을 펼친 포트별 입력한 이름.
 * @property error 마지막 선언을 core가 거부한 이유.
 */
data class PortsState(
    val project: String? = null,
    val ports: Load<List<ObservedPort>>? = null,
    val names: Map<Int, String> = emptyMap(),
    val error: String? = null
)

/**
 * 포트 탭. core가 운영체제에서 관찰한 열린 포트(`GET /projects/{p}/ports`)를 보인다. 포트 번호나
 * 명령을 짐작하지 않는다. 선언 밖 포트는 이름을 적어 `runs:`에 선언으로 저장한다(core가 그
 * 프로세스의 명령줄과 작업 폴더를 쓴다).
 */
class PortsViewModel(private val api: RunsApi, private val scope: CoroutineScope) {

    private val _state = MutableStateFlow(PortsState())
    val state: StateFlow<PortsState> = _state.asStateFlow()

    fun open(project: String) {
        if (_state.value.project == project) return
        _state.value = PortsState(project = project)
        reload()
    }

    fun close() {
        _state.value = PortsState()
    }

    fun reload() {
        val project = _state.value.project ?: return
        _state.update { it.copy(ports = it.ports.takeIf { p -> p is Load.Ready } ?: Load.Loading) }
        scope.launch {
            val ports = loadOf { api.listPorts(project).bodyOrThrow() }
            _state.update { if (it.project == project) it.copy(ports = ports) else it }
        }
    }

    /** [port]의 "선언으로 저장"을 펼친다(이름 입력칸). 이미 펼쳤으면 접는다. */
    fun toggleDeclare(port: Int) = _state.update {
        it.copy(names = if (port in it.names) it.names - port else it.names + (port to ""))
    }

    fun setName(port: Int, name: String) = _state.update {
        if (port in it.names) it.copy(names = it.names + (port to name)) else it
    }

    /** 입력한 이름으로 [port]를 `runs:`에 선언한다. 이름이 비었으면 보내지 않는다. */
    fun declare(port: Int) {
        val project = _state.value.project ?: return
        val name = _state.value.names[port]?.trim()?.takeIf { it.isNotEmpty() } ?: return
        _state.update { it.copy(error = null) }
        scope.launch {
            val declared =
                loadOf { api.declarePort(project, port, PortDeclare(name)).bodyOrThrow() }
            _state.update {
                when {
                    it.project != project -> it
                    declared is Load.Failed -> it.copy(error = declared.message)
                    else -> it.copy(names = it.names - port)
                }
            }
            reload()
        }
    }

    /** `ports.changed`. 보고 있는 프로젝트면 이벤트의 목록으로 바꾼다. */
    fun onChanged(project: String, ports: List<ObservedPort>) = _state.update {
        if (it.project == project) it.copy(ports = Load.Ready(ports)) else it
    }
}
