"""선언된 실행 대상 하나의 프로세스: 시작·출력·열기 대기·정지.

프로세스는 새 세션(프로세스 그룹)으로 띄워 정지할 때 자손까지 함께
끝낸다. 표준 출력과 표준 오류는 합쳐 한 줄씩 이벤트로 넘긴다.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from madang.config import RunTarget
from madang.runs.declare import RunsError, check_cwd
from madang.runs.ports import Listen, listening_ports

RUN_STARTED = "runs.started"
RUN_OUTPUT = "runs.output"
RUN_OPEN = "runs.open"
RUN_EXITED = "runs.exited"
RUN_STOPPED = "runs.stopped"

STOP_SECONDS = 5.0
OPENS_SECONDS = 30.0
POLL_SECONDS = 0.2

# (이벤트 이름, 내용) -> None
OnEvent = Callable[[str, dict[str, Any]], None]


def _ignore(name: str, payload: dict[str, Any]) -> None:
    """이벤트를 받을 곳이 없을 때 쓴다."""


class Process:
    """core가 소유한 실행 대상 프로세스 하나.

    Attributes:
        target: 선언된 실행 대상.
        root: 프로젝트 폴더.
    """

    def __init__(
        self, target: RunTarget, root: Path, on_event: OnEvent | None = None
    ) -> None:
        self.target = target
        self.root = root
        self._emit = on_event or _ignore
        self._popen: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._stopping = False

    @property
    def cwd(self) -> Path:
        """명령을 실행하는 폴더."""
        return self.root / self.target.cwd

    @property
    def pid(self) -> int | None:
        """프로세스 그룹의 뿌리 pid. 시작 전이면 None."""
        return self._popen.pid if self._popen is not None else None

    @property
    def running(self) -> bool:
        """프로세스가 아직 살아 있는지 여부."""
        return self._popen is not None and self._popen.poll() is None

    @property
    def returncode(self) -> int | None:
        """종료 코드. 아직 돌고 있거나 시작 전이면 None."""
        return self._popen.poll() if self._popen is not None else None

    def start(self) -> None:
        """선언된 명령을 ``cwd``에서 셸로 실행한다.

        Raises:
            RunsError: 이미 돌고 있거나 ``cwd``가 올바르지 않다.
            OSError: 프로세스를 띄울 수 없다.
        """
        if self.running:
            raise RunsError(f"run '{self.target.name}' is already running")
        check_cwd(self.target.cwd, self.root)
        if not self.cwd.is_dir():
            raise RunsError(f"run cwd {self.cwd} does not exist")
        self._stopping = False
        self._popen = subprocess.Popen(
            self.target.command,
            shell=True,
            cwd=self.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self._emit(RUN_STARTED, {**self._about(), "pid": self._popen.pid})
        self._reader = threading.Thread(
            target=self._pump, args=(self._popen,), daemon=True
        )
        self._reader.start()

    def _pump(self, popen: subprocess.Popen[str]) -> None:
        """출력을 한 줄씩 넘기고, 끝나면 종료를 알린다."""
        assert popen.stdout is not None
        for line in popen.stdout:
            self._emit(RUN_OUTPUT, {**self._about(), "line": line.rstrip()})
        code = popen.wait()
        kind = RUN_STOPPED if self._stopping else RUN_EXITED
        self._emit(kind, {**self._about(), "code": code})

    def wait(self, timeout: float | None = None) -> int:
        """프로세스가 끝나고 출력을 다 넘길 때까지 기다린다.

        Returns:
            종료 코드.

        Raises:
            RunsError: 시작하지 않았다.
            subprocess.TimeoutExpired: 시간 안에 끝나지 않았다.
        """
        if self._popen is None:
            raise RunsError(f"run '{self.target.name}' was not started")
        code = self._popen.wait(timeout)
        if self._reader is not None:
            self._reader.join(timeout)
        return code

    def stop(self, timeout: float = STOP_SECONDS) -> int | None:
        """프로세스 그룹을 끝낸다. 시간 안에 안 끝나면 강제로 끝낸다.

        Returns:
            종료 코드. 시작하지 않았으면 None.
        """
        if self._popen is None:
            return None
        self._stopping = self.running
        deadline = time.monotonic() + timeout
        if _signal_group(self._popen.pid, signal.SIGTERM):
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._popen.wait(timeout)
            left = max(0.0, deadline - time.monotonic())
            if not _await_group(self._popen.pid, left):
                _signal_group(self._popen.pid, signal.SIGKILL)
        return self.wait(timeout)

    def restart(self) -> None:
        """정지한 뒤 다시 시작한다."""
        self.stop()
        self.start()

    def wait_opens(
        self, timeout: float = OPENS_SECONDS, poll: float = POLL_SECONDS
    ) -> bool:
        """``opens`` URL이 응답할 때까지 기다린 뒤 열기 이벤트를 낸다.

        HTTP 오류 응답도 서버가 응답한 것으로 본다. 프로세스가 먼저
        끝나거나 시간이 다 되면 포기한다.

        Args:
            timeout: 기다릴 최대 초.
            poll: 확인 간격 초.

        Returns:
            응답을 받아 열기 이벤트를 냈는지 여부. ``opens``가 없으면
            거짓.
        """
        url = self.target.opens
        if not url:
            return False
        deadline = time.monotonic() + timeout
        while self.running and time.monotonic() < deadline:
            if responds(url):
                self._emit(RUN_OPEN, {**self._about(), "url": url})
                return True
            time.sleep(poll)
        return False

    def ports(self) -> list[Listen]:
        """이 프로세스 트리가 지금 LISTEN 중인 포트."""
        if not self.running or self.pid is None:
            return []
        return listening_ports(self.pid)

    def _about(self) -> dict[str, Any]:
        return {"name": self.target.name, "root": str(self.root)}


def responds(url: str, timeout: float = 1.0) -> bool:
    """``url``에 HTTP 요청을 보내 어떤 응답이든 오는지 반환한다."""
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except (OSError, ValueError):
        return False


def _signal_group(pid: int, sig: signal.Signals) -> bool:
    """그룹에 신호를 보낸다. 그룹이 없으면 거짓."""
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return False
    return True


def _await_group(pid: int, timeout: float) -> bool:
    """그룹이 사라질 때까지 기다린다. 사라졌으면 참."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS / 2)
