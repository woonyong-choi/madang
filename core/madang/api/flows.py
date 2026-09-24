"""메시지 흐름을 백그라운드 스레드에서 돌리고 그 이벤트를 앱에 알린다.

페이지마다 한 번에 흐름 하나만 돈다. 흐름 id는 ``<page-id>/<메시지 id>``
이고, 사람을 기다리는 결정의 id는 그 메시지 id다. 정책이 부작용을 멈추면
page.md에 묻는 블록이 생기고, 그 블록 id로도 답할 수 있다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from madang.api import errors, events
from madang.graph import Flow
from madang.graph import events as flow_events
from madang.graph.nodes import (
    WAIT_BLOCKED,
    WAIT_KIND,
    WAIT_NO_RUNNER,
    WAIT_POLICY,
    WAIT_REPAIR,
    WAIT_REVIEW,
    WAIT_RUN_LIMIT,
)
from madang.store import pages, projects, runs, summary
from madang.store.page import LEDGER_FILE
from madang.validate import count_tokens

log = logging.getLogger(__name__)

JOIN_SECONDS = 5.0
PROMPTS = {
    WAIT_KIND: "요청 종류를 정하지 못했습니다. 어떤 종류로 처리할까요?",
    WAIT_BLOCKED: "마지막 단계까지 올려도 막혔습니다. 다시 시도할까요?",
    WAIT_RUN_LIMIT: "메시지 하나의 실행 한도에 닿았습니다. 계속할까요?",
    WAIT_REPAIR: "ledger.md 보정에 실패했습니다. 어떻게 할까요?",
    WAIT_REVIEW: "리뷰 실행이 실패했습니다. 다시 시도할까요?",
    WAIT_NO_RUNNER: (
        "쓸 수 있는 도구가 없습니다(대체 도구 포함). 로그인한 뒤 다시 "
        "시도할까요?"
    ),
    WAIT_POLICY: (
        "정책(테스트·충돌·금지 명령)이 머지나 게시를 멈췄습니다. "
        "묻는 블록의 이유를 보고 답해 주세요."
    ),
}


def waiting_data(
    page_dir: Path, thread_id: str, decision: dict[str, Any]
) -> dict[str, Any]:
    """흐름이 기다리는 질문을 ``FlowWaitingData`` 형태로 반환한다.

    Args:
        page_dir: 페이지 폴더.
        thread_id: 흐름 id.
        decision: 흐름 상태의 ``pending_decision``.

    Returns:
        ``{decision: {id, run, question, ask?, reasons?}, reason}``. 정책이
        멈춘 결정이면 묻는 블록 id(``ask``)와 거부 사유가 있다.
    """
    reason = str(decision.get("reason") or "")
    pending: dict[str, Any] = {
        "id": thread_id.rsplit("/", 1)[-1],
        "run": runs.current(page_dir),
        "question": {
            "kind": "choice",
            "prompt": PROMPTS.get(reason, "어떻게 할까요?"),
            "options": list(decision.get("options") or []),
        },
    }
    if decision.get("block"):
        pending["ask"] = str(decision["block"])
        pending["reasons"] = [str(r) for r in decision.get("reasons") or []]
    return {"decision": pending, "reason": reason}


@dataclass
class _Active:
    flow: Flow
    thread: threading.Thread | None = None
    known: set[str] = field(default_factory=set)
    runner: str | None = None


class Flows:
    """페이지별 흐름 실행과 그 이벤트 번역."""

    def __init__(self, core: Any) -> None:
        self._core = core
        self._lock = threading.Lock()
        self._active: dict[str, _Active] = {}
        self._threads: dict[str, threading.Thread] = {}

    def busy(self, page_id: str) -> bool:
        """그 페이지에서 흐름이 돌고 있는지 여부."""
        with self._lock:
            return page_id in self._active

    def start(
        self, page_dir: Path, text: str, target: dict[str, Any] | None
    ) -> str:
        """메시지를 남기고 흐름을 백그라운드에서 시작한다.

        Args:
            page_dir: 페이지 폴더.
            text: 메시지 본문.
            target: ``{block, elements, mode}``. 페이지 전체면 None.

        Returns:
            저장한 메시지 블록 id.

        Raises:
            HttpError: 흐름이 이미 돌고 있다(409 busy).
            ValidationFailureError: 대상 블록이 없다.
        """
        page_id = page_dir.name
        active = self._claim(page_id)
        try:
            with self._core.lock:
                thread_id, state = active.flow.accept(page_id, text, target)
        except ValueError as exc:
            self._release(page_id)
            raise errors.invalid(str(exc)) from exc
        except BaseException:
            self._release(page_id)
            raise
        message = thread_id.rsplit("/", 1)[-1]
        before = set(
            pages.read_header(page_dir / "page.md").get("blocks") or []
        )
        before.discard(message)
        active.known = self._core.announce_blocks(page_dir, before)
        self._core.announce_page(page_dir, events.PAGE_UPDATED)
        self._launch(
            page_id, active, lambda: active.flow.advance(thread_id, state)
        )
        return message

    def answer(self, page_dir: Path, decision_id: str, choice: str) -> None:
        """기다리는 흐름에 답하고 백그라운드에서 이어 간다.

        Args:
            page_dir: 페이지 폴더.
            decision_id: ``flow.waiting``의 결정 id(메시지 id).
            choice: 선택지 중 하나.

        Raises:
            HttpError: 흐름이 기다리지 않거나(404) 이미 돌고 있다(409).
            ValidationFailureError: 선택지에 없는 답이다.
        """
        page_id = page_dir.name
        thread_id = f"{page_id}/{decision_id}"
        active = self._claim(page_id)
        try:
            waiting = active.flow.waiting(thread_id)
            if waiting is None:
                raise errors.not_found(
                    f"decision '{decision_id}' is not waiting for an answer"
                )
            if choice not in waiting["options"]:
                raise errors.invalid(
                    f"choice '{choice}' is not one of {waiting['options']}"
                )
        except BaseException:
            self._release(page_id)
            raise
        active.known = set(
            pages.read_header(page_dir / "page.md").get("blocks") or []
        )
        self._launch(
            page_id, active, lambda: active.flow.resume(thread_id, choice)
        )

    def answer_ask(self, page_dir: Path, block: str, choice: str) -> None:
        """묻는 블록 ``block``을 기다리는 흐름에 답한다.

        Raises:
            HttpError: 그 블록을 기다리는 흐름이 없거나(404) 흐름이 이미
                돌고 있다(409).
            ValidationFailureError: 선택지에 없는 답이다.
        """
        if self.busy(page_dir.name):
            raise errors.conflict(
                f"a flow is already running on page '{page_dir.name}'",
                errors.BUSY,
            )
        flow = self._flow()
        for thread_id, decision in flow.waiting_on(page_dir.name):
            if decision.get("block") == block:
                message = thread_id.rsplit("/", 1)[-1]
                self.answer(page_dir, message, choice)
                return
        raise errors.not_found(f"ask block '{block}' is not waiting")

    def cancel(self, page_dir: Path, n: int) -> bool:
        """진행 중인 실행 ``n``을 멈춘다.

        Returns:
            멈추기 시작했으면 참. 그 실행이 진행 중이 아니면 거짓.
        """
        with self._lock:
            active = self._active.get(page_dir.name)
        if active is None or runs.current(page_dir) != n:
            return False
        if runs.record_path(page_dir, n).is_file():
            return False
        active.flow.cancel()
        return True

    def runner(self, page_id: str) -> str | None:
        """그 페이지에서 지금 실행 중인 러너 이름. 없으면 None."""
        with self._lock:
            active = self._active.get(page_id)
        return active.runner if active is not None else None

    def waiting(self, page_dir: Path) -> dict[str, Any] | None:
        """페이지에서 가장 최근에 멈춘 흐름의 질문. 없으면 None."""
        if self.busy(page_dir.name):
            return None
        flow = self._flow()
        found = flow.waiting_on(page_dir.name)
        if not found:
            return None
        thread_id, decision = found[-1]
        return waiting_data(page_dir, thread_id, decision)

    def join(self, page_id: str, timeout: float | None = None) -> None:
        """그 페이지의 흐름이 끝날 때까지 기다린다."""
        with self._lock:
            thread = self._threads.get(page_id)
        if thread is not None:
            thread.join(timeout)

    def shutdown(self) -> None:
        """돌고 있는 흐름을 모두 멈추고 잠시 기다린다."""
        with self._lock:
            actives = list(self._active.values())
        for active in actives:
            active.flow.cancel()
        for active in actives:
            if active.thread is not None:
                active.thread.join(JOIN_SECONDS)

    # 내부

    def _claim(self, page_id: str) -> _Active:
        with self._lock:
            if page_id in self._active:
                raise errors.conflict(
                    f"a flow is already running on page '{page_id}'",
                    errors.BUSY,
                )
            active = _Active(flow=self._new_flow(page_id))
            self._active[page_id] = active
            return active

    def _release(self, page_id: str) -> None:
        with self._lock:
            self._active.pop(page_id, None)

    def _new_flow(self, page_id: str) -> Flow:
        return self._flow(
            lambda name, payload: self._relay(page_id, name, payload)
        )

    def _flow(
        self, on_event: flow_events.EventHook = flow_events.ignore
    ) -> Flow:
        return Flow(
            self._core.config(),
            runners=self._core.make_runner,
            on_event=on_event,
            availability=self._core.availability,
        )

    def _launch(
        self, page_id: str, active: _Active, body: Callable[[], Any]
    ) -> None:
        def main() -> None:
            try:
                body()
            except Exception:
                log.exception("flow on page %s failed", page_id)
            finally:
                self._release(page_id)
                self._settle(page_id, active)

        active.thread = threading.Thread(
            target=main, name=f"flow-{page_id}", daemon=True
        )
        with self._lock:
            self._threads[page_id] = active.thread
        active.thread.start()

    def _settle(self, page_id: str, active: _Active) -> None:
        """흐름이 끝나거나 멈춘 뒤 남은 변경을 알린다."""
        try:
            page_dir = pages.find_page(self._core.home, page_id)
        except pages.PageNotFoundError:
            return
        active.known = self._core.announce_blocks(page_dir, active.known)
        self._core.announce_page(page_dir, events.PAGE_UPDATED)

    # 흐름 이벤트 번역

    def _relay(self, page_id: str, name: str, payload: dict[str, Any]) -> None:
        try:
            page_dir = pages.find_page(self._core.home, page_id)
            self._translate(page_dir, name, payload)
        except Exception:
            log.exception("cannot relay %s for page %s", name, page_id)

    def _translate(
        self, page_dir: Path, name: str, payload: dict[str, Any]
    ) -> None:
        project = projects.owner(self._core.home, page_dir).id
        where = {"project": project, "page": page_dir.name}
        hub = self._core.hub
        if name == flow_events.RUN_STARTED:
            with self._lock:
                if (active := self._active.get(page_dir.name)) is not None:
                    active.runner = payload.get("runner")
            keys = ("runner", "model", "effort", "kind", "tier")
            data = {k: payload[k] for k in keys if payload.get(k) is not None}
            hub.emit(name, data, run=_next_run(page_dir), **where)
        elif name == flow_events.RUN_FALLBACK:
            keys = ("from", "to", "reason")
            data = {k: payload[k] for k in keys}
            hub.emit(name, data, run=_next_run(page_dir), **where)
        elif name == flow_events.RUN_ASSEMBLED:
            data = summary.run_input(payload["input"]) or {}
            hub.emit(name, data, run=_next_run(page_dir), **where)
        elif name == flow_events.RUN_PROGRESS:
            hub.emit(name, payload["event"], run=payload["n"], **where)
        elif name in (flow_events.RUN_FINISHED, flow_events.RUN_FAILED):
            self._finished(page_dir, name, payload, where)
        elif name == flow_events.PAGE_UNKNOWN_FILES:
            files = [{"path": p, "run": payload["n"]} for p in payload["files"]]
            hub.emit(name, {"files": files}, run=payload["n"], **where)
        elif name == flow_events.FLOW_WAITING:
            data = waiting_data(
                page_dir, payload["thread_id"], payload["decision"]
            )
            run = runs.current(page_dir)
            hub.emit(name, data, run=run, **where)
            if "ask" in data["decision"]:
                self._ask_created(data["decision"], run, where)
        elif name == flow_events.FLOW_SETTLED:
            self._settled(page_dir, payload, where)

    def _ask_created(
        self, pending: dict[str, Any], run: int | None, where: dict[str, str]
    ) -> None:
        """정책이 멈춘 자리에 생긴 묻는 블록을 ``ask.created``로 알린다."""
        data = {
            "block": pending["ask"],
            "decision": pending["id"],
            "prompt": pending["question"]["prompt"],
            "reasons": pending.get("reasons") or [],
            "options": pending["question"]["options"],
        }
        self._core.hub.emit(
            events.ASK_CREATED, data, run=run, block=pending["ask"], **where
        )

    def _settled(
        self, page_dir: Path, payload: dict[str, Any], where: dict[str, str]
    ) -> None:
        """정책 단계가 한 머지와 게시를 ``git.changed``·``publish.done``으로."""
        root = projects.owner(self._core.home, page_dir).root
        if payload.get("merged"):
            self._core.announce_git(
                where["project"], root, "merge", commit=payload["merged"]
            )
        if payload.get("published") is not None:
            data = {
                "n": payload["published"],
                "undo": False,
                "push_error": payload.get("push_error"),
            }
            self._core.hub.emit(
                events.PUBLISH_DONE, data, run=payload.get("n"), **where
            )

    def _finished(
        self,
        page_dir: Path,
        name: str,
        payload: dict[str, Any],
        where: dict[str, str],
    ) -> None:
        n = payload["n"]
        record = runs.read_run(page_dir, n)
        if name == flow_events.RUN_FINISHED:
            data = summary.run_record(record)
        else:
            status = payload.get("status") or "error"
            data = {
                "result_status": status,
                "error": payload.get("error") or status,
            }
        self._core.hub.emit(name, data, run=n, **where)
        with self._lock:
            active = self._active.get(page_dir.name)
        if active is not None:
            active.known = self._core.announce_blocks(
                page_dir, active.known, run=n
            )
        if LEDGER_FILE in record.changed_files:
            text = (page_dir / LEDGER_FILE).read_text(encoding="utf-8")
            self._core.announce_memory("ledger", count_tokens(text), page_dir)
        self._core.announce_page(page_dir, events.PAGE_UPDATED)


def _next_run(page_dir: Path) -> int:
    """곧 시작할 실행의 번호. 페이지마다 흐름이 하나라 겹치지 않는다."""
    return (runs.current(page_dir) or 0) + 1
