package madang.shared.main

import kotlinx.coroutines.CoroutineScope
import madang.api.client.FilesApi
import madang.api.client.GitApi
import madang.api.client.MemoryApi
import madang.api.client.RunnersApi
import madang.api.client.RunsApi
import madang.api.model.GitChangedEvent
import madang.api.model.MemoryUpdatedEvent
import madang.api.model.PortsChangedEvent
import madang.api.model.RunFailedEvent
import madang.api.model.RunFinishedEvent
import madang.api.model.RunProgressEvent
import madang.shared.core.CoreClient

/**
 * 오른쪽 사이드바 탭들의 ViewModel. 보이는 탭 하나만 core에서 내용을 받고, 나머지는 닫아 둔다.
 * 기록 탭은 열린 페이지의 run 목록([historyRows])이라 따로 받지 않는다.
 */
class SidebarTabs(core: CoreClient, scope: CoroutineScope) {
    private val runsApi = core.api(::RunsApi)

    val memory = MemoryViewModel(core.api(::MemoryApi), scope)
    val now = NowViewModel(runsApi, core.api(::RunnersApi), scope)
    val files = FilesViewModel(core.api(::FilesApi), runsApi, scope)
    val git = GitViewModel(core.api(::GitApi), scope)
    val ports = PortsViewModel(runsApi, scope)

    private var sidebar = Sidebar()

    /**
     * 사이드바나 열린 페이지가 바뀌었다. 보이는 탭을 [project]·[page]로 열고 나머지는 닫는다. 지금
     * 탭은 보일 때마다 사용량을 다시 받는다.
     */
    fun sync(next: Sidebar, project: String?, page: String?) {
        val shown = next.tab.takeIf { next.open }
        val nowShown = shown == SideTab.NOW && (sidebar.tab != SideTab.NOW || !sidebar.open)
        sidebar = next
        if (shown == SideTab.MEMORY && page != null) memory.open(page) else memory.close()
        if (shown == SideTab.FILES && project != null) files.open(project, page) else files.close()
        if (shown == SideTab.GIT && project != null) git.open(project, page) else git.close()
        if (shown == SideTab.PORTS && project != null) ports.open(project) else ports.close()
        if (nowShown) now.refreshUsage()
    }

    /** 사이드바가 쓰는 이벤트를 탭에 나눠 준다. */
    fun onEvent(payload: Any) {
        when (payload) {
            is RunProgressEvent -> now.onProgress(payload)

            is RunFinishedEvent -> ended(payload.project)

            is RunFailedEvent -> ended(payload.project)

            is GitChangedEvent -> {
                files.onChanged(payload.project)
                git.onChanged(payload.project)
            }

            is PortsChangedEvent -> ports.onChanged(payload.project, payload.data.ports)

            is MemoryUpdatedEvent -> memory.onUpdated(payload.page, payload.data.layer)
        }
    }

    /** run이 끝나면 작업 트리와 사용량이 바뀌었을 수 있다. */
    private fun ended(project: String) {
        files.onChanged(project)
        if (sidebar.open && sidebar.tab == SideTab.NOW) now.refreshUsage()
    }
}
