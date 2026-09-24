"""사용 기록 파일(JSON 줄)을 찾고 읽는 공통 도구."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def jsonl_files(bases: Iterable[Path], start: datetime) -> list[Path]:
    """폴더들 아래에서 ``start`` 뒤에 고친 ``*.jsonl``. 없는 폴더는 건너뛴다."""
    since = start.timestamp()
    found: set[Path] = set()
    for base in bases:
        if base.is_dir():
            found.update(base.rglob("*.jsonl"))
    recent = []
    for path in sorted(found):
        try:
            if path.is_file() and path.stat().st_mtime >= since:
                recent.append(path)
        except OSError:
            continue
    return recent


def json_lines(path: Path, needle: str = "") -> Iterator[dict[str, Any]]:
    """파일의 JSON 객체 줄. ``needle``이 없는 줄과 깨진 줄은 건너뛴다."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        if needle not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            yield record


def parse_time(value: Any) -> datetime | None:
    """ISO 8601 시각. 시간대가 없으면 UTC로 본다. 못 읽으면 ``None``."""
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def text(value: Any) -> str | None:
    """앞뒤 공백을 뺀 비지 않은 문자열. 아니면 ``None``."""
    if not isinstance(value, str):
        return None
    return value.strip() or None
