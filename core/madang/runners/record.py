"""Runs a runner for a page and keeps its run record and event log.

The record is ``runs/N.json`` and the log is ``runs/N.events.jsonl``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from madang.config import Config
from madang.runners.base import CliRunner, RunEvent, RunResult
from madang.store import runs


@dataclass
class RecordedRun:
    """A finished run and where its record was written.

    Attributes:
        n: The run number.
        result: The runner result.
        record: The record written to ``runs/N.json``.
        path: The path of that record.
    """

    n: int
    result: RunResult
    record: runs.RunRecord
    path: Path


def timeout_seconds(config: Config, kind: str) -> float | None:
    """Returns the run timeout for ``kind``.

    Args:
        config: The loaded app home configuration.
        kind: The run kind.

    Returns:
        ``limits.run_timeout_minutes[kind]`` in seconds, or None when unset.
    """
    minutes = config.madang.limits.run_timeout_minutes.get(kind)
    return float(minutes) * 60 if minutes else None


def run_page(
    runner: CliRunner,
    *,
    config: Config,
    page_dir: Path,
    cwd: Path,
    prompt: str,
    model: str,
    effort: str,
    kind: str,
    on_event: Callable[[RunEvent], None] = lambda _event: None,
    tier: int | None = None,
    trigger: dict[str, Any] | None = None,
    input: dict[str, Any] | None = None,
) -> RecordedRun:
    """Allocates the next run number, runs, and writes the run record.

    The page id (folder name) is passed to the agent as ``MADANG_PAGE``.

    Args:
        runner: The runner to use.
        config: The loaded app home configuration.
        page_dir: The page folder.
        cwd: The working directory of the run.
        prompt: The prompt.
        model: The model name.
        effort: The reasoning effort.
        kind: The run kind. Selects the timeout.
        on_event: Called with each event as it arrives.
        tier: The routing tier, if any.
        trigger: What started the run, if recorded.
        input: The run input, if recorded.

    Returns:
        The finished run.
    """
    n = runs.allocate(page_dir)
    started = datetime.now().astimezone()
    result = runner.exec(
        cwd=cwd,
        prompt=prompt,
        model=model,
        effort=effort,
        on_event=on_event,
        page=page_dir.name,
        timeout=timeout_seconds(config, kind),
        events_log=runs.events_path(page_dir, n),
    )
    record = runs.RunRecord(
        n=n,
        started=started,
        finished=datetime.now().astimezone(),
        trigger=trigger,
        kind=kind,
        tier=tier,
        runner=runner.name,
        model=model,
        effort=effort,
        input=input,
        usage=runs.RunUsage(
            input=result.usage.input,
            cached=result.usage.cached,
            output=result.usage.output,
        ),
        changed_files=[
            _relative(p, page_dir, cwd) for p in result.changed_files
        ],
        result_status=result.status,
        events_log=runs.events_rel(n),
    )
    path = runs.write_run(page_dir, record)
    return RecordedRun(n=n, result=result, record=record, path=path)


def _relative(path: str, page_dir: Path, cwd: Path) -> str:
    """Page-relative when inside the page, else cwd-relative, else as given."""
    p = Path(path)
    if not p.is_absolute():
        p = cwd / p
    p = p.resolve()
    for base in (page_dir, cwd):
        try:
            return p.relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return path
