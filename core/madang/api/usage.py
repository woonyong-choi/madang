"""구독 사용량: Claude Code가 남긴 대화 기록에서 토큰 사용을 센다.

``~/.claude/projects/<폴더>/<세션>.jsonl``의 ``assistant`` 줄에 있는
``message.usage``만 읽는다. 인증·설정 파일은 읽지 않는다. 한 응답이 여러
줄로 나뉘어 같은 사용량이 되풀이되므로 ``message.id``와 ``requestId``로
한 번만 센다. 기록이 없으면 도구를 ``available: false``로 돌려준다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECTS_DIR = "projects"
TOOL = "claude"
DEFAULT_DAYS = 7
_FIELDS = (
    ("input_tokens", "input_tokens"),
    ("output_tokens", "output_tokens"),
    ("cache_read_tokens", "cache_read_input_tokens"),
    ("cache_creation_tokens", "cache_creation_input_tokens"),
)


@dataclass
class _Totals:
    messages: int = 0
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, usage: dict[str, Any]) -> None:
        self.messages += 1
        for name, key in _FIELDS:
            value = usage.get(key)
            if isinstance(value, int):
                self.counts[name] += value

    def to_dict(self) -> dict[str, int]:
        return {
            "messages": self.messages,
            **{name: self.counts[name] for name, _ in _FIELDS},
        }


def claude_usage(claude_dir: Path, since: date) -> dict[str, Any]:
    """``since`` 이후(그날 포함) Claude Code의 토큰 사용 합계.

    Args:
        claude_dir: Claude Code 폴더(보통 ``~/.claude``).
        since: 셀 첫날(로컬 날짜).

    Returns:
        ``ToolUsage`` 형태: 합계, 세션 수, 모델별·날짜별 합계.
    """
    base = claude_dir / PROJECTS_DIR
    total, models, days = _Totals(), defaultdict(_Totals), defaultdict(_Totals)
    sessions: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for record in _records(base, since):
        message = record.get("message") or {}
        usage = message.get("usage")
        stamp = _local_day(record.get("timestamp"))
        if not isinstance(usage, dict) or stamp is None or stamp < since:
            continue
        key = (str(message.get("id") or ""), str(record.get("requestId") or ""))
        if key != ("", ""):
            if key in seen:
                continue
            seen.add(key)
        total.add(usage)
        models[str(message.get("model") or "unknown")].add(usage)
        days[stamp.isoformat()].add(usage)
        sessions.add(str(record.get("sessionId") or ""))
    return {
        "tool": TOOL,
        "available": base.is_dir(),
        "sessions": len(sessions - {""}),
        **total.to_dict(),
        "models": [
            {"model": name, **models[name].to_dict()} for name in sorted(models)
        ],
        "days": [{"date": day, **days[day].to_dict()} for day in sorted(days)],
    }


def _records(base: Path, since: date) -> Iterator[dict[str, Any]]:
    """``since`` 이후 고친 세션 파일의 JSON 줄. 깨진 줄은 건너뛴다."""
    if not base.is_dir():
        return
    start = datetime.combine(since, datetime.min.time()).timestamp()
    for path in sorted(base.rglob("*.jsonl")):
        try:
            if path.stat().st_mtime < start:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in lines.splitlines():
            if '"usage"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("type") == "assistant":
                yield record


def _local_day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone().date()
