"""러너 프로토콜, 도구에 중립적인 실행 이벤트, 공용 CLI 구동기.

실행마다 새 CLI 프로세스를 시작한다. 어댑터는 도구의 JSON 스트림 한 줄을
``RunEvent`` 값으로 바꾸는 방식만 다르다.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from madang.config import HOME_ENV, RunnerSpec

PAGE_ENV = "MADANG_PAGE"
CORE_URL_ENV = "MADANG_CORE_URL"

EventType = Literal[
    "text", "tool_call", "tool_result", "file_changed", "usage", "done", "error"
]
RunStatus = Literal["done", "error", "blocked", "cancelled"]

SUMMARY_LIMIT = 200
KILL_GRACE_SECONDS = 5.0
STDERR_TAIL_LINES = 50


@dataclass(frozen=True)
class Usage:
    """토큰 수. ``input``은 캐시된 토큰을 포함한다."""

    input: int = 0
    cached: int = 0
    output: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input + other.input,
            self.cached + other.cached,
            self.output + other.output,
        )


@dataclass(frozen=True)
class RunEvent:
    """정규화된 이벤트 하나. ``type``에 속한 필드만 채운다.

    text: ``text`` · tool_call: ``name``, ``summary`` ·
    tool_result: ``summary`` · file_changed: ``path`` · usage: ``usage`` ·
    done: ``text``(최종 답) · error: ``message``.
    """

    type: EventType
    text: str | None = None
    name: str | None = None
    summary: str | None = None
    path: str | None = None
    usage: Usage | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """값이 있는 필드를 JSON에 바로 쓸 수 있는 dict로 반환한다."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RunResult:
    """실행 한 번의 결과.

    Attributes:
        status: 실행이 끝난 방식.
        usage: 도구가 보고한 토큰 수.
        final_text: 최종 답.
        events_log: 원본 스트림을 담은 파일. 없을 수 있다.
        exit_code: 프로세스 종료 코드. 시작하지 못했으면 None.
        duration: 실제 경과 시간(초).
        error: 실행이 끝나지 못했다면 그 이유.
        events: 실행 중 발생한 모든 이벤트.
    """

    status: RunStatus
    usage: Usage = field(default_factory=Usage)
    final_text: str = ""
    events_log: Path | None = None
    exit_code: int | None = None
    duration: float = 0.0
    error: str | None = None
    events: list[RunEvent] = field(default_factory=list)

    @property
    def changed_files(self) -> list[str]:
        """``file_changed`` 이벤트의 경로. 처음 나온 순서."""
        seen: dict[str, None] = {}
        for event in self.events:
            if event.type == "file_changed" and event.path:
                seen.setdefault(event.path)
        return list(seen)


class Runner(Protocol):
    """에이전트 턴 하나를 실행하고 이벤트를 보고하는 것."""

    name: str

    def exec(
        self,
        *,
        cwd: Path,
        prompt: str,
        model: str,
        effort: str,
        on_event: Callable[[RunEvent], None],
    ) -> RunResult:
        """한 번 실행하고 끝날 때까지 블록한다."""
        ...


def summarize(value: Any, limit: int = SUMMARY_LIMIT) -> str:
    """``value``를 최대 ``limit``자의 한 줄로 반환한다.

    Args:
        value: 문자열 또는 JSON 직렬화 가능한 값.
        limit: 최대 길이. 더 긴 줄은 말줄임표로 끝난다.

    Returns:
        요약 줄.
    """
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    line = " ".join(value.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


class StreamParser(Protocol):
    """디코딩된 JSON 줄을 이벤트로 바꾸고 실행 결과를 보관한다."""

    final_text: str
    usage: Usage | None
    error: str | None
    finished: bool

    def feed(self, obj: dict[str, Any]) -> list[RunEvent]:
        """디코딩된 JSON 한 줄에 대한 이벤트를 반환한다."""
        ...


_VAR = re.compile(r"\{([a-z_]+)\}")


def render_args(args: list[str], values: Mapping[str, str | None]) -> list[str]:
    """러너 인자의 ``{name}`` 자리표시자를 치환한다.

    Args:
        args: 인자 템플릿.
        values: 자리표시자 값. None이면 이번 실행에서 미설정.

    Returns:
        치환된 인자.

    Raises:
        ValueError: 자리표시자를 모르거나 값이 없다.
    """

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise ValueError(f"unknown runner argument variable {{{name}}}")
        value = values[name]
        if value is None:
            raise ValueError(
                f"runner argument variable {{{name}}} has no value for this run"
            )
        return value

    return [_VAR.sub(sub, arg) for arg in args]


class CliRunner:
    """구독형 CLI를 새 서브프로세스로 실행하고 스트림을 파싱한다.

    하위 클래스는 ``name``을 정하고 ``new_parser``를 구현한다.

    Attributes:
        spec: CLI를 시작하는 방법.
        home: 에이전트에 넘길 앱 홈.
        core_url: 에이전트에 넘길 core API URL. 없을 수 있다.
        kill_grace: 중지할 때 SIGTERM과 SIGKILL 사이의 초.
    """

    name: str = ""

    def __init__(
        self,
        spec: RunnerSpec,
        *,
        home: Path,
        core_url: str | None = None,
        kill_grace: float = KILL_GRACE_SECONDS,
    ) -> None:
        self.spec = spec
        self.home = Path(home)
        self.core_url = core_url
        self.kill_grace = kill_grace
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._stop_reason: RunStatus | None = None

    def new_parser(self) -> StreamParser:
        """실행 하나의 스트림용 새 파서를 반환한다."""
        raise NotImplementedError

    def command(
        self,
        *,
        cwd: Path,
        prompt: str,
        model: str,
        effort: str,
        page: str | None = None,
    ) -> list[str]:
        """실행 한 번의 명령줄을 만든다.

        인자가 프롬프트 위치를 정하지 않으면 ``--`` 뒤에 프롬프트를 붙인다.

        Args:
            cwd: 실행의 작업 디렉터리.
            prompt: 프롬프트.
            model: 모델 이름.
            effort: 추론 강도.
            page: 페이지 id. 실행이 페이지에 속하는 경우.

        Returns:
            명령과 그 인자.

        Raises:
            ValueError: 인자 자리표시자를 모르거나 값이 없다.
        """
        values = {
            "model": model,
            "effort": effort,
            "home": str(self.home),
            "cwd": str(cwd),
            "page": page,
            "prompt": prompt,
        }
        uses_prompt = any("{prompt}" in arg for arg in self.spec.args)
        args = render_args(self.spec.args, values)
        if not uses_prompt:
            # "--"는 "-"로 시작하는 프롬프트가 옵션으로 읽히지 않게 한다.
            args += ["--", prompt]
        return [self.spec.bin, *args]

    def environment(self, page: str | None) -> dict[str, str]:
        """Madang 변수를 설정한 프로세스 환경을 반환한다.

        Args:
            page: 페이지 id. None이면 ``MADANG_PAGE``를 제거한다.

        Returns:
            madang 변수를 적용한 ``os.environ`` 복사본.
        """
        env = dict(os.environ)
        env[HOME_ENV] = str(self.home)
        if page:
            env[PAGE_ENV] = page
        else:
            env.pop(PAGE_ENV, None)
        if self.core_url:
            env[CORE_URL_ENV] = self.core_url
        return env

    def exec(
        self,
        *,
        cwd: Path,
        prompt: str,
        model: str,
        effort: str,
        on_event: Callable[[RunEvent], None],
        page: str | None = None,
        timeout: float | None = None,
        events_log: Path | None = None,
    ) -> RunResult:
        """한 번 실행하고 프로세스가 끝날 때까지 블록한다.

        Args:
            cwd: 실행의 작업 디렉터리.
            prompt: 프롬프트.
            model: 모델 이름.
            effort: 추론 강도.
            on_event: 이벤트가 도착할 때마다 호출된다.
            page: 페이지 id. 실행이 페이지에 속하는 경우.
            timeout: 프로세스 그룹 전체를 중지하고 실행을
                ``blocked``로 끝내기까지의 초.
            events_log: 원본 스트림을 줄 단위로 덧붙일 파일.

        Returns:
            실행 결과.

        Raises:
            ValueError: 인자 자리표시자를 모르거나 값이 없다.
        """
        cmd = self.command(
            cwd=cwd, prompt=prompt, model=model, effort=effort, page=page
        )
        parser = self.new_parser()
        events: list[RunEvent] = []

        def emit(event: RunEvent) -> None:
            events.append(event)
            on_event(event)

        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=self.environment(page),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            message = f"cannot start {self.spec.bin}: {exc}"
            emit(RunEvent("error", message=message))
            return RunResult(
                status="error",
                error=message,
                events=events,
                events_log=events_log,
            )

        with self._lock:
            self._proc = proc
            self._stop_reason = None

        stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        drain = threading.Thread(
            target=_drain, args=(proc.stderr, stderr_tail), daemon=True
        )
        drain.start()
        timer = (
            threading.Timer(timeout, self._stop, args=("blocked",))
            if timeout
            else None
        )
        if timer:
            timer.daemon = True
            timer.start()

        log = None
        if events_log is not None:
            events_log.parent.mkdir(parents=True, exist_ok=True)
            log = events_log.open("a", encoding="utf-8")
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if log:
                    log.write(line if line.endswith("\n") else line + "\n")
                    log.flush()
                obj = _decode(line)
                if obj is not None:
                    for event in parser.feed(obj):
                        emit(event)
            exit_code = proc.wait()
        except BaseException:
            self._stop("error")
            raise
        finally:
            if timer:
                timer.cancel()
            if log:
                log.close()
            drain.join(timeout=1)
            with self._lock:
                self._proc = None
        duration = round(time.monotonic() - started, 3)

        status, error = _outcome(
            self._stop_reason, parser, exit_code, stderr_tail, timeout
        )
        if status == "done":
            emit(RunEvent("done", text=parser.final_text))
        elif error and error != parser.error:
            emit(RunEvent("error", message=error))

        return RunResult(
            status=status,
            usage=parser.usage or Usage(),
            final_text=parser.final_text,
            events_log=events_log,
            exit_code=exit_code,
            duration=duration,
            error=error,
            events=events,
        )

    def cancel(self) -> None:
        """실행 중인 프로세스 그룹이 있으면 중지한다.

        실행은 ``cancelled``로 끝난다.
        """
        self._stop("cancelled")

    def _stop(self, reason: RunStatus) -> None:
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None:
                return
            if self._stop_reason is None:
                self._stop_reason = reason
        _kill_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=self.kill_grace)
        except subprocess.TimeoutExpired:
            _kill_group(proc, signal.SIGKILL)


def _kill_group(proc: subprocess.Popen[str], sig: signal.Signals) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, sig)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass


def _drain(stream: Any, tail: deque[str]) -> None:
    for line in stream:
        tail.append(line.rstrip("\n"))


def _decode(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _outcome(
    stop: RunStatus | None,
    parser: StreamParser,
    exit_code: int,
    stderr_tail: deque[str],
    timeout: float | None,
) -> tuple[RunStatus, str | None]:
    if stop == "blocked":
        return "blocked", f"timed out after {timeout:g}s"
    if stop == "cancelled":
        return "cancelled", "cancelled"
    if parser.error or exit_code != 0 or not parser.finished:
        return "error", parser.error or _failure_message(
            exit_code, stderr_tail, parser.finished
        )
    return "done", None


def _failure_message(
    exit_code: int, stderr_tail: deque[str], finished: bool
) -> str:
    lines = [line for line in stderr_tail if line.strip()]
    if lines:
        return summarize(" | ".join(lines[-3:]), 500)
    if exit_code != 0:
        return f"exited with code {exit_code}"
    return (
        "stream ended without a final result" if not finished else "run failed"
    )
