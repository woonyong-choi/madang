"""Runner protocol, tool-neutral run events, and the shared CLI subprocess driver.

Every run starts a fresh CLI process. The adapter only differs in how it turns
one line of the tool's JSON stream into ``RunEvent`` values.
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

EventType = Literal["text", "tool_call", "tool_result", "file_changed", "usage", "done", "error"]
RunStatus = Literal["done", "error", "blocked", "cancelled"]

SUMMARY_LIMIT = 200
KILL_GRACE_SECONDS = 5.0
STDERR_TAIL_LINES = 50


@dataclass(frozen=True)
class Usage:
    """Token counts. ``input`` includes cached tokens."""

    input: int = 0
    cached: int = 0
    output: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input + other.input, self.cached + other.cached, self.output + other.output)


@dataclass(frozen=True)
class RunEvent:
    """One normalized event. Only the fields that belong to ``type`` are set.

    text: ``text`` · tool_call: ``name``, ``summary`` · tool_result: ``summary`` ·
    file_changed: ``path`` · usage: ``usage`` · done: ``text`` (final answer) ·
    error: ``message``.
    """

    type: EventType
    text: str | None = None
    name: str | None = None
    summary: str | None = None
    path: str | None = None
    usage: Usage | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RunResult:
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
        seen: dict[str, None] = {}
        for event in self.events:
            if event.type == "file_changed" and event.path:
                seen.setdefault(event.path)
        return list(seen)


class Runner(Protocol):
    name: str

    def exec(
        self,
        *,
        cwd: Path,
        prompt: str,
        model: str,
        effort: str,
        on_event: Callable[[RunEvent], None],
    ) -> RunResult: ...


def summarize(value: Any, limit: int = SUMMARY_LIMIT) -> str:
    """One line, at most ``limit`` characters."""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    line = " ".join(value.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


class StreamParser(Protocol):
    """Turns decoded JSON lines into events and keeps the run's outcome."""

    final_text: str
    usage: Usage | None
    error: str | None
    finished: bool

    def feed(self, obj: dict[str, Any]) -> list[RunEvent]: ...


_VAR = re.compile(r"\{([a-z_]+)\}")


def render_args(args: list[str], values: Mapping[str, str | None]) -> list[str]:
    """Substitute ``{name}`` placeholders. Unknown or unset names are errors."""

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise ValueError(f"unknown runner argument variable {{{name}}}")
        value = values[name]
        if value is None:
            raise ValueError(f"runner argument variable {{{name}}} has no value for this run")
        return value

    return [_VAR.sub(sub, arg) for arg in args]


class CliRunner:
    """Runs a subscription CLI as a fresh subprocess and parses its JSON stream."""

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
        raise NotImplementedError

    def command(
        self, *, cwd: Path, prompt: str, model: str, effort: str, page: str | None = None
    ) -> list[str]:
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
            # "--" keeps a prompt that starts with "-" from being read as an option.
            args += ["--", prompt]
        return [self.spec.bin, *args]

    def environment(self, page: str | None) -> dict[str, str]:
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
        """Run once and block until the process ends.

        ``timeout`` is in seconds; when it passes, the whole process group is
        stopped and the result status is ``blocked``. The raw stream is copied
        line by line to ``events_log`` when given.
        """
        cmd = self.command(cwd=cwd, prompt=prompt, model=model, effort=effort, page=page)
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
            return RunResult(status="error", error=message, events=events, events_log=events_log)

        with self._lock:
            self._proc = proc
            self._stop_reason = None

        stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        drain = threading.Thread(target=_drain, args=(proc.stderr, stderr_tail), daemon=True)
        drain.start()
        timer = threading.Timer(timeout, self._stop, args=("blocked",)) if timeout else None
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

        stop = self._stop_reason
        error: str | None = None
        if stop == "blocked":
            status: RunStatus = "blocked"
            error = f"timed out after {timeout:g}s"
        elif stop == "cancelled":
            status = "cancelled"
            error = "cancelled"
        elif parser.error or exit_code != 0 or not parser.finished:
            status = "error"
            error = parser.error or _failure_message(exit_code, stderr_tail, parser.finished)
        else:
            status = "done"

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
        """Stop the running process group, if any. The run ends as ``cancelled``."""
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


def _failure_message(exit_code: int, stderr_tail: deque[str], finished: bool) -> str:
    lines = [line for line in stderr_tail if line.strip()]
    if lines:
        return summarize(" | ".join(lines[-3:]), 500)
    if exit_code != 0:
        return f"exited with code {exit_code}"
    return "stream ended without a final result" if not finished else "run failed"
