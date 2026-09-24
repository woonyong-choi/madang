"""Run records: ``runs/N.json`` summaries and ``runs/N.events.jsonl`` raw streams.

Run numbers grow inside a page and are never reused, even after a record is
deleted: the last number handed out is kept in ``runs/.last``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

RUNS_DIR = "runs"
LAST_FILE = ".last"

_NUMBERED = re.compile(r"^(\d+)\.(?:json|events\.jsonl)$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class RunUsage(_Model):
    input: int = 0
    cached: int = 0
    output: int = 0


class RunVerify(_Model):
    cmd: str | None = None
    ok: bool | None = None


class RunRecord(_Model):
    """Content of ``runs/N.json``. Unknown keys are kept."""

    n: int
    started: datetime | None = None
    finished: datetime | None = None
    trigger: dict[str, Any] | None = None
    kind: str | None = None
    tier: int | None = None
    runner: str | None = None
    model: str | None = None
    effort: str | None = None
    input: dict[str, Any] | None = None
    usage: RunUsage = Field(default_factory=RunUsage)
    changed_files: list[str] = Field(default_factory=list)
    unknown_files: list[str] = Field(default_factory=list)
    verify: RunVerify = Field(default_factory=RunVerify)
    result_status: str | None = None
    commit: str | None = None
    events_log: str | None = None


def runs_dir(page_dir: Path) -> Path:
    return page_dir / RUNS_DIR


def record_path(page_dir: Path, n: int) -> Path:
    return runs_dir(page_dir) / f"{n}.json"


def events_path(page_dir: Path, n: int) -> Path:
    return runs_dir(page_dir) / f"{n}.events.jsonl"


def events_rel(n: int) -> str:
    """``events_log`` value as stored in the record (relative to the page)."""
    return f"{RUNS_DIR}/{n}.events.jsonl"


def list_runs(page_dir: Path) -> list[int]:
    """Numbers that have a ``N.json`` record, ascending."""
    runs = runs_dir(page_dir)
    if not runs.is_dir():
        return []
    return sorted(
        int(p.stem) for p in runs.iterdir() if p.is_file() and re.fullmatch(r"\d+\.json", p.name)
    )


def _highest(page_dir: Path) -> int:
    runs = runs_dir(page_dir)
    high = 0
    last = runs / LAST_FILE
    if last.is_file():
        text = last.read_text(encoding="utf-8").strip()
        if text.isdigit():
            high = int(text)
    for p in runs.iterdir():
        if m := _NUMBERED.match(p.name):
            high = max(high, int(m.group(1)))
    return high


def current(page_dir: Path) -> int | None:
    """Last run number handed out for the page (the run in progress, if any)."""
    if not runs_dir(page_dir).is_dir():
        return None
    return _highest(page_dir) or None


def allocate(page_dir: Path) -> int:
    """Reserve the next run number by creating an empty ``N.events.jsonl``."""
    runs = runs_dir(page_dir)
    runs.mkdir(parents=True, exist_ok=True)
    n = _highest(page_dir) + 1
    while True:
        try:
            fd = os.open(events_path(page_dir, n), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            n += 1
            continue
        os.close(fd)
        break
    _atomic_write(runs / LAST_FILE, f"{n}\n")
    return n


def write_run(page_dir: Path, record: RunRecord) -> Path:
    path = record_path(page_dir, record.n)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.model_dump(mode="json")
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def read_run(page_dir: Path, n: int) -> RunRecord:
    path = record_path(page_dir, n)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: invalid JSON: {exc}") from exc
    return RunRecord.model_validate(data)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
