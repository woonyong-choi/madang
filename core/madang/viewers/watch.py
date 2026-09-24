"""live 뷰어 정본 폴더 감시.

등록부의 ``follow: live`` 항목을 주기적으로 훑어(폴링) 파일 목록·크기·
수정 시각이 바뀐 뷰어의 이름을 콜백으로 알린다. 폴더가 사라지거나
다시 생겨도 바뀐 것으로 본다. 처음 보는 항목은 기준만 잡고 알리지 않는다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from madang.viewers.registry import FOLLOW_LIVE, Registry

log = logging.getLogger(__name__)

type Fingerprint = tuple[tuple[str, int, int], ...] | None


def fingerprint(folder: Path) -> Fingerprint:
    """폴더 안 파일의 ``(상대 경로, 크기, 수정 시각 ns)`` 목록.

    Args:
        folder: 뷰어 폴더.

    Returns:
        정렬된 튜플. 폴더가 없으면 None.
    """
    if not folder.is_dir():
        return None
    found = []
    for path in folder.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(folder).parts:
            continue
        stat = path.stat()
        rel = path.relative_to(folder).as_posix()
        found.append((rel, stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(found))


class ViewerWatcher:
    """live 뷰어가 바뀌면 이름을 알린다.

    Args:
        registry: 감시할 등록부. 훑을 때마다 다시 읽는다.
        on_change: 바뀐 뷰어 이름을 받는 함수.
        interval: 백그라운드로 훑는 간격(초).
    """

    def __init__(
        self,
        registry: Registry,
        on_change: Callable[[str], None],
        interval: float = 1.0,
    ) -> None:
        self._registry = registry
        self._on_change = on_change
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._prints = self._snapshot()

    def poll(self) -> list[str]:
        """한 번 훑고 바뀐 뷰어 이름을 알린 뒤 반환한다."""
        current = self._snapshot()
        changed = [
            name
            for name, print_ in current.items()
            if name in self._prints and self._prints[name] != print_
        ]
        self._prints = current
        for name in changed:
            self._on_change(name)
        return changed

    def start(self) -> None:
        """백그라운드 스레드에서 ``interval``마다 훑기 시작한다."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="viewer-watch", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """백그라운드 훑기를 멈추고 스레드가 끝날 때까지 기다린다."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except Exception:
                log.exception("viewer watch failed")

    def _snapshot(self) -> dict[str, Fingerprint]:
        return {
            entry.name: fingerprint(entry.source)
            for entry in self._registry.entries()
            if entry.follow == FOLLOW_LIVE
        }
