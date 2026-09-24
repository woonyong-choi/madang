"""흐름이 노드마다 알리는 이벤트의 이름과 받는 쪽 형태."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

RUN_STARTED = "run.started"
RUN_ASSEMBLED = "run.assembled"
RUN_PROGRESS = "run.progress"
RUN_FINISHED = "run.finished"
RUN_FAILED = "run.failed"
RUN_FALLBACK = "run.fallback"
FLOW_WAITING = "flow.waiting"
FLOW_SETTLED = "flow.settled"
PAGE_UNKNOWN_FILES = "page.unknown_files"

EventHook = Callable[[str, dict[str, Any]], None]
"""``(이름, 내용)``을 받는 콜백. 내용은 JSON으로 바로 보낼 수 있는 dict다."""


def ignore(name: str, payload: dict[str, Any]) -> None:
    """이벤트를 버린다. 받는 쪽이 없을 때의 기본값."""
