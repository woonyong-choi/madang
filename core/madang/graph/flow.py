"""메시지 하나를 처리하는 흐름 그래프와 그 시작·재개·취소.

흐름: classify → pick → assemble → run → validate → (repair) → judge →
(review_run | 승격 | ask_human) → finish. 체크포인트는 앱 홈의
``core.db``(SQLite)에 남아, 사람의 답을 기다리는 흐름은 core가 다시
시작해도 이어 갈 수 있다.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from madang.config import Config
from madang.graph import events
from madang.graph.nodes import FlowNodes, RunnerFactory
from madang.graph.state import FlowState, initial_state
from madang.runners import make_runner
from madang.store import pages, projects
from madang.store.log import append_message

DB_FILE = "core.db"


@dataclass
class FlowResult:
    """흐름이 끝났거나 멈춘 뒤의 모습.

    Attributes:
        thread_id: 흐름 id. 재개할 때 쓴다.
        state: 마지막 상태.
        waiting: 사람에게 묻는 중이면 그 질문, 아니면 None.
    """

    thread_id: str
    state: FlowState
    waiting: dict[str, Any] | None


def build_graph(nodes: FlowNodes) -> StateGraph:
    """노드를 이어 컴파일 전의 그래프를 반환한다.

    Args:
        nodes: 노드 함수.

    Returns:
        그래프.
    """
    graph = StateGraph(FlowState)
    graph.add_node("classify", nodes.classify, destinations=("pick",))
    graph.add_node("pick", nodes.pick)
    graph.add_node("assemble", nodes.assemble)
    graph.add_node("run", nodes.run, destinations=("validate", END))
    graph.add_node(
        "validate",
        nodes.validate,
        destinations=("judge", "repair", "ask_human"),
    )
    graph.add_node("repair", nodes.repair, destinations=("judge", "ask_human"))
    graph.add_node(
        "judge",
        nodes.judge,
        destinations=("finish", "review_run", "pick", "ask_human", END),
    )
    graph.add_node("review_run", nodes.review_run, destinations=("validate",))
    graph.add_node("finish", nodes.finish)
    graph.add_node(
        "ask_human",
        nodes.ask_human,
        destinations=("pick", "repair", "review_run", END),
    )
    graph.add_edge(START, "classify")
    graph.add_edge("pick", "assemble")
    graph.add_edge("assemble", "run")
    graph.add_edge("finish", END)
    return graph


@contextmanager
def checkpointer(home: Path) -> Iterator[SqliteSaver]:
    """앱 홈의 ``core.db``를 여는 체크포인터를 낸다.

    Args:
        home: 앱 홈.

    Yields:
        SQLite 체크포인터. 블록을 나가면 연결을 닫는다.
    """
    conn = sqlite3.connect(Path(home) / DB_FILE, check_same_thread=False)
    with closing(conn):
        yield SqliteSaver(conn)


class Flow:
    """앱 홈 하나에서 흐름을 시작하고, 재개하고, 취소한다.

    Attributes:
        cfg: 앱 홈 설정.
    """

    def __init__(
        self,
        cfg: Config,
        *,
        runners: RunnerFactory = make_runner,
        on_event: events.EventHook = events.ignore,
    ) -> None:
        self.cfg = cfg
        self._nodes = FlowNodes(cfg, runners, on_event, threading.Event())

    def start(
        self,
        page_id: str,
        request: str,
        target: dict[str, Any] | None = None,
    ) -> FlowResult:
        """메시지를 페이지 로그에 남기고 그 메시지의 흐름을 실행한다.

        Args:
            page_id: 페이지 id.
            request: 메시지 본문.
            target: ``{block, elements, mode}``. 페이지 전체면 None.

        Returns:
            끝났거나 사람을 기다리는 흐름.

        Raises:
            PageNotFoundError: 페이지가 없는 경우.
            ValueError: 대상 블록에 파일이 없는 경우.
        """
        thread_id, state = self.accept(page_id, request, target)
        return self.advance(thread_id, state)

    def accept(
        self,
        page_id: str,
        request: str,
        target: dict[str, Any] | None = None,
    ) -> tuple[str, FlowState]:
        """메시지를 페이지 로그에 남기고 흐름의 첫 상태를 만든다.

        그래프는 실행하지 않는다. 호출자가 ``advance``로 이어 간다.

        Args:
            page_id: 페이지 id.
            request: 메시지 본문.
            target: ``{block, elements, mode}``. 페이지 전체면 None.

        Returns:
            ``(흐름 id, 첫 상태)``. 흐름 id는 ``<page-id>/<메시지 id>``다.

        Raises:
            PageNotFoundError: 페이지가 없는 경우.
            ValueError: 대상 블록에 파일이 없는 경우.
        """
        page_dir = pages.find_page(self.cfg.home, page_id)
        target = _normalize(target)
        block = target["block"]
        if block is not None and not pages.block_files(page_dir, block):
            raise ValueError(f"block '{block}' has no file in blocks/")
        message = append_message(
            page_dir, "user", request, {"target": block or "page"}
        )
        project = projects.owner(self.cfg.home, page_dir).id
        state = initial_state(project, page_dir.name, message, target)
        return f"{page_dir.name}/{message}", state

    def advance(self, thread_id: str, state: FlowState) -> FlowResult:
        """``accept``가 만든 첫 상태로 흐름을 실행한다.

        Args:
            thread_id: ``accept``가 돌려준 흐름 id.
            state: ``accept``가 돌려준 첫 상태.

        Returns:
            끝났거나 사람을 기다리는 흐름.
        """
        self._nodes.cancelled.clear()
        return self._invoke(state, thread_id)

    def resume(self, thread_id: str, choice: str) -> FlowResult:
        """사람을 기다리는 흐름에 답을 주고 이어 간다.

        Args:
            thread_id: 흐름 id.
            choice: 질문의 선택지 중 하나.

        Returns:
            끝났거나 다시 사람을 기다리는 흐름.

        Raises:
            ValueError: 흐름이 기다리고 있지 않거나 선택지에 없는 답인 경우.
        """
        waiting = self.waiting(thread_id)
        if waiting is None:
            raise ValueError(f"flow '{thread_id}' is not waiting for an answer")
        if choice not in waiting["options"]:
            raise ValueError(
                f"choice '{choice}' is not one of {waiting['options']}"
            )
        self._nodes.cancelled.clear()
        return self._invoke(Command(resume=choice), thread_id)

    def waiting(self, thread_id: str) -> dict[str, Any] | None:
        """흐름이 사람을 기다리면 그 질문을, 아니면 None을 반환한다."""
        with self._compiled() as graph:
            return _pending(graph, thread_id)

    def waiting_on(self, page_id: str) -> list[tuple[str, dict[str, Any]]]:
        """페이지에서 사람의 답을 기다리는 흐름을 찾는다.

        ``core.db``의 체크포인트에서 그 페이지의 흐름 id를 모두 훑는다.

        Args:
            page_id: 페이지 id.

        Returns:
            ``(흐름 id, 질문)`` 목록. 메시지 순서(오래된 것 먼저).
        """
        prefix = f"{page_id}/"
        with self._compiled() as graph:
            threads = [
                thread
                for thread in _thread_ids(graph.checkpointer)
                if thread.startswith(prefix)
            ]
            found = [
                (thread, pending)
                for thread in sorted(threads, key=_message_order)
                if (pending := _pending(graph, thread)) is not None
            ]
        return found

    def cancel(self) -> None:
        """진행 중인 실행을 멈추고 흐름을 끝낸다. 실행 직전이어도 멈춘다."""
        self._nodes.cancel()

    @contextmanager
    def _compiled(self) -> Iterator[CompiledStateGraph]:
        with checkpointer(self.cfg.home) as saver:
            yield build_graph(self._nodes).compile(checkpointer=saver)

    def _invoke(self, value: Any, thread_id: str) -> FlowResult:
        with self._compiled() as graph:
            graph.invoke(value, _config(thread_id))
            state = graph.get_state(_config(thread_id)).values
            return FlowResult(
                thread_id=thread_id,
                state=FlowState(**state),
                waiting=_pending(graph, thread_id),
            )


def resume(
    thread_id: str,
    choice: str,
    *,
    cfg: Config,
    runners: RunnerFactory = make_runner,
    on_event: events.EventHook = events.ignore,
) -> FlowResult:
    """사람을 기다리는 흐름에 답을 주고 이어 간다.

    Args:
        thread_id: 흐름 id.
        choice: 질문의 선택지 중 하나. 종류 질문이면 종류 이름, 아니면
            ``retry`` 또는 ``stop``.
        cfg: 앱 홈 설정.
        runners: 러너 이름으로 러너를 만든다.
        on_event: 이벤트를 받는 콜백.

    Returns:
        끝났거나 다시 사람을 기다리는 흐름.

    Raises:
        ValueError: 흐름이 기다리고 있지 않거나 선택지에 없는 답인 경우.
    """
    flow = Flow(cfg, runners=runners, on_event=on_event)
    return flow.resume(thread_id, choice)


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _pending(graph: CompiledStateGraph, thread_id: str) -> dict | None:
    snapshot = graph.get_state(_config(thread_id))
    if not snapshot.next:
        return None
    return snapshot.values.get("pending_decision")


def _thread_ids(saver: SqliteSaver) -> list[str]:
    """체크포인트가 있는 흐름 id. 아직 표가 없으면 빈 목록."""
    try:
        rows = saver.conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [str(row[0]) for row in rows]


def _message_order(thread_id: str) -> tuple[int, str]:
    """``<page>/bNN`` 흐름 id를 메시지 번호로 정렬하는 키."""
    message = thread_id.rsplit("/", 1)[-1]
    number = pages.parse_block_id(message)
    return (number if number is not None else -1, thread_id)


def _normalize(target: dict[str, Any] | None) -> dict[str, Any]:
    target = target or {}
    block = target.get("block")
    return {
        "block": block,
        "elements": list(target.get("elements") or []),
        "mode": target.get("mode") or (None if block is None else "edit"),
    }
