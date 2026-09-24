"""Run a runner for a page and keep ``runs/N.json`` and ``runs/N.events.jsonl``."""

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
    n: int
    result: RunResult
    record: runs.RunRecord
    path: Path


def timeout_seconds(config: Config, kind: str) -> float | None:
    """``limits.run_timeout_minutes[kind]`` in seconds, ``None`` when not set."""
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
    """Allocate the next run number, execute, and write the summary record.

    The page id (folder name) is passed to the agent as ``MADANG_PAGE``.
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
            input=result.usage.input, cached=result.usage.cached, output=result.usage.output
        ),
        changed_files=[_relative(p, page_dir, cwd) for p in result.changed_files],
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
