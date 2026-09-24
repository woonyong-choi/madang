"""프로젝트들의 실행 대상 프로세스를 이름으로 맡아 두는 감독."""

from __future__ import annotations

import threading
from pathlib import Path

from madang.runs.declare import RunsError, find
from madang.runs.ports import Listen
from madang.runs.process import OnEvent, Process


class Supervisor:
    """core가 띄운 실행 대상 프로세스 목록.

    같은 프로젝트의 같은 이름은 한 번에 하나만 돈다. 실행할 수 있는 것은
    ``runs:``에 선언된 것뿐이다.
    """

    def __init__(self, on_event: OnEvent | None = None) -> None:
        self._on_event = on_event
        self._procs: dict[tuple[Path, str], Process] = {}
        self._lock = threading.Lock()

    def start(self, root: Path, name: str) -> Process:
        """선언된 실행 대상을 시작한다.

        Raises:
            RunsError: 선언이 없거나 이미 돌고 있다.
            OSError: 설정을 읽거나 프로세스를 띄울 수 없다.
        """
        target = find(root, name)
        key = (root.resolve(), name)
        with self._lock:
            current = self._procs.get(key)
            if current is not None and current.running:
                raise RunsError(f"run '{name}' is already running")
            proc = Process(target, root, self._on_event)
            proc.start()
            self._procs[key] = proc
        return proc

    def get(self, root: Path, name: str) -> Process:
        """맡고 있는 프로세스를 반환한다.

        Raises:
            RunsError: 시작한 적이 없다.
        """
        proc = self._procs.get((root.resolve(), name))
        if proc is None:
            raise RunsError(f"run '{name}' has not been started")
        return proc

    def stop(self, root: Path, name: str) -> int | None:
        """프로세스 그룹을 정지하고 종료 코드를 반환한다."""
        return self.get(root, name).stop()

    def restart(self, root: Path, name: str) -> Process:
        """정지한 뒤 선언을 다시 읽어 시작한다."""
        self.stop(root, name)
        return self.start(root, name)

    def ports(self, root: Path, name: str) -> list[Listen]:
        """그 프로세스 트리가 지금 LISTEN 중인 포트."""
        return self.get(root, name).ports()

    def running(self) -> list[Process]:
        """아직 돌고 있는 프로세스."""
        return [proc for proc in self._procs.values() if proc.running]

    def stop_all(self) -> None:
        """돌고 있는 모든 프로세스를 정지한다. core가 끝날 때 쓴다."""
        for proc in self.running():
            proc.stop()
