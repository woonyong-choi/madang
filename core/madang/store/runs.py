"""실행 기록: ``runs/N.json`` 요약과 ``runs/N.jsonl`` 원본 스트림.

``N.jsonl``은 러너가 낸 줄을 손대지 않고 담는다. 요약은 스트림과 섞지 않고
별도 파일 ``N.json``에 둔다.

실행 번호는 페이지 안에서 늘어나며 기록이 삭제돼도 다시 쓰지 않는다.
마지막으로 내준 번호는 ``runs/.last``에 보관한다.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from madang.store.files import atomic_write

RUNS_DIR = "runs"
LAST_FILE = ".last"

_NUMBERED = re.compile(r"^(\d+)\.jsonl?$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class RunUsage(_Model):
    """실행의 토큰 수. ``input``은 캐시된 토큰을 포함한다."""

    input: int = 0
    cached: int = 0
    output: int = 0


class RunVerify(_Model):
    """실행의 검증 명령과 통과 여부."""

    cmd: str | None = None
    ok: bool | None = None


class RunRecord(_Model):
    """``runs/N.json``의 내용. 알 수 없는 키는 보존한다."""

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
    events_log: str | None = None
    contract: str | None = None
    duration: float | None = None
    error: str | None = None
    state_check: dict[str, Any] | None = None


def runs_dir(page_dir: Path) -> Path:
    """페이지의 ``runs/`` 폴더를 반환한다."""
    return page_dir / RUNS_DIR


def record_path(page_dir: Path, n: int) -> Path:
    """``runs/N.json``의 경로를 반환한다."""
    return runs_dir(page_dir) / f"{n}.json"


def events_path(page_dir: Path, n: int) -> Path:
    """원본 스트림 ``runs/N.jsonl``의 경로를 반환한다."""
    return page_dir / events_rel(n)


def events_rel(n: int) -> str:
    """기록에 저장하는 ``events_log`` 값(페이지 기준 상대 경로)을 반환한다."""
    return f"{RUNS_DIR}/{n}.jsonl"


def list_runs(page_dir: Path) -> list[int]:
    """``N.json`` 기록이 있는 번호를 오름차순으로 반환한다."""
    runs = runs_dir(page_dir)
    if not runs.is_dir():
        return []
    return sorted(
        int(p.stem)
        for p in runs.iterdir()
        if p.is_file() and re.fullmatch(r"\d+\.json", p.name)
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
    """페이지에 마지막으로 내준 실행 번호를 반환한다.

    진행 중인 실행이 있으면 그 실행이다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        실행 번호. 페이지에 아직 실행이 없으면 None.
    """
    if not runs_dir(page_dir).is_dir():
        return None
    return _highest(page_dir) or None


def allocate(page_dir: Path) -> int:
    """빈 ``N.jsonl``을 만들어 다음 실행 번호를 예약한다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        새 실행 번호.
    """
    runs = runs_dir(page_dir)
    runs.mkdir(parents=True, exist_ok=True)
    n = _highest(page_dir) + 1
    while True:
        try:
            fd = os.open(
                events_path(page_dir, n),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError:
            n += 1
            continue
        os.close(fd)
        break
    atomic_write(runs / LAST_FILE, f"{n}\n")
    return n


def write_run(page_dir: Path, record: RunRecord) -> Path:
    """``record``를 ``runs/N.json``에 원자적으로 쓴다.

    Args:
        page_dir: 페이지 폴더.
        record: 실행 기록.

    Returns:
        쓴 경로.
    """
    path = record_path(page_dir, record.n)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.model_dump(mode="json")
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def read_run(page_dir: Path, n: int) -> RunRecord:
    """``runs/N.json``을 읽는다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호.

    Returns:
        실행 기록.

    Raises:
        OSError: 파일을 읽을 수 없다.
        ValueError: 파일이 올바른 JSON이 아니거나 올바른 기록이 아니다.
    """
    path = record_path(page_dir, n)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: invalid JSON: {exc}") from exc
    return RunRecord.model_validate(data)
