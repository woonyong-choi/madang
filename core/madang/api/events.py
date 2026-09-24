"""이벤트: 봉투 ``{type, ts, project?, page?, block?, run?, data}``와 전달.

앱은 ``/events`` WebSocket 하나로 모든 변경을 받는다. 이벤트는 어느
스레드에서든 낼 수 있고, 연결마다 그 연결의 이벤트 루프로 넘긴다.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder

PROJECT_CREATED = "project.created"
PROJECT_UPDATED = "project.updated"
PROJECT_DELETED = "project.deleted"
PAGE_CREATED = "page.created"
PAGE_UPDATED = "page.updated"
PAGE_DELETED = "page.deleted"
BLOCK_ADDED = "block.added"
BLOCK_UPDATED = "block.updated"
BLOCK_DELETED = "block.deleted"
MEMORY_UPDATED = "memory.updated"
RUNNER_AVAILABILITY = "runner.availability"


def make_event(
    kind: str,
    data: dict[str, Any],
    *,
    project: str | None = None,
    page: str | None = None,
    block: str | None = None,
    run: int | None = None,
) -> dict[str, Any]:
    """이벤트 봉투를 만든다. 값이 없는 선택 키는 넣지 않는다.

    Args:
        kind: 이벤트 종류. 예: ``page.updated``.
        data: 종류별 내용.
        project: 프로젝트 id.
        page: 페이지 id.
        block: 블록 id.
        run: 실행 번호.

    Returns:
        JSON으로 보낼 이벤트. 시각은 문자열로 바꾸고 값이 없는 키는 뺀다.
    """
    event: dict[str, Any] = {
        "type": kind,
        "ts": datetime.now().astimezone().replace(microsecond=0).isoformat(),
    }
    for key, value in (
        ("project", project),
        ("page", page),
        ("block", block),
        ("run", run),
    ):
        if value is not None:
            event[key] = value
    event["data"] = _compact(jsonable_encoder(data))
    return event


def _compact(value: Any) -> Any:
    """값이 None인 키를 뺀다. HTTP 응답과 같이 "없음"은 키를 두지 않는다."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


class EventHub:
    """연결된 WebSocket마다 이벤트를 나눠 준다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: list[
            tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]
        ] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """현재 이벤트 루프에서 받을 큐를 등록한다. 루프 안에서 부른다."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._queues.append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """등록한 큐를 뺀다."""
        with self._lock:
            self._queues = [(lp, q) for lp, q in self._queues if q is not queue]

    def publish(self, event: dict[str, Any]) -> None:
        """모든 연결에 이벤트를 보낸다. 어느 스레드에서든 부를 수 있다."""
        with self._lock:
            targets = list(self._queues)
        for loop, queue in targets:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:  # 루프가 이미 닫혔다
                self.unsubscribe(queue)

    def emit(self, kind: str, data: dict[str, Any], **where: Any) -> None:
        """``make_event``로 만든 이벤트를 보낸다."""
        self.publish(make_event(kind, data, **where))
