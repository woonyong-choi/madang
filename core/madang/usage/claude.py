"""Claude Code가 남긴 대화 기록에서 응답별 토큰 사용을 읽는다.

Orca(MIT)의 ``src/main/claude-usage/transcript-record-parser.ts``와
``transcript-file-discovery.ts``를 옮겼다. ``~/.claude/projects``와
``~/.claude/transcripts`` 아래 ``*.jsonl``의 ``assistant`` 줄에 있는
``message.usage``만 읽는다. 인증·설정 파일은 읽지 않는다. 한 응답이 여러
줄로 되풀이되므로 ``message.id``·``requestId``(없으면 ``uuid``)로 묶고,
뒤의 줄이 더 완전할 수 있어 항목별로 큰 값을 남긴다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from madang.usage.records import json_lines, jsonl_files, parse_time, text
from madang.usage.report import Turn

TOOL = "claude"
ROOTS = ("projects", "transcripts")
_FIELDS = (
    ("input_tokens", "input_tokens"),
    ("output_tokens", "output_tokens"),
    ("cache_read_tokens", "cache_read_input_tokens"),
    ("cache_creation_tokens", "cache_creation_input_tokens"),
)


def available(claude_dir: Path) -> bool:
    """대화 기록 폴더가 하나라도 있는지."""
    return any((claude_dir / root).is_dir() for root in ROOTS)


def read_turns(claude_dir: Path, start: datetime) -> list[Turn]:
    """``start`` 뒤에 고친 기록 파일의 응답들. 되풀이된 응답은 하나로 묶는다.

    Args:
        claude_dir: Claude Code 폴더(보통 ``~/.claude``).
        start: 이보다 먼저 고친 파일은 읽지 않는다.
    """
    turns: dict[str, Turn] = {}
    loose: list[Turn] = []
    bases = [claude_dir / root for root in ROOTS]
    for path in jsonl_files(bases, start):
        # 파일 내용을 통째로 담은 사용자 줄은 해석하기 전에 거른다.
        for record in json_lines(path, needle="assistant"):
            turn = parse_record(record, path.stem)
            if turn is None:
                continue
            key = dedupe_key(record)
            if key is None:
                loose.append(turn)
            elif key in turns:
                turns[key] = _larger(turns[key], turn)
            else:
                turns[key] = turn
    return [*turns.values(), *loose]


def parse_record(record: dict[str, Any], fallback_session: str) -> Turn | None:
    """``assistant`` 기록 하나를 ``Turn``으로. 토큰이 없으면 ``None``."""
    if record.get("type") != "assistant":
        return None
    session = record.get("sessionId") or fallback_session
    stamp = parse_time(record.get("timestamp"))
    message = record.get("message")
    if not session or stamp is None or not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    counts = {name: _count(usage.get(key)) for name, key in _FIELDS}
    if sum(counts.values()) <= 0:
        return None
    return Turn(
        timestamp=stamp,
        session=str(session),
        model=str(message.get("model") or "unknown"),
        **counts,
    )


def dedupe_key(record: dict[str, Any]) -> str | None:
    """같은 응답의 되풀이를 묶는 열쇠. 포크된 기록에서도 유지되는 것부터."""
    message = record.get("message") or {}
    message_id = text(message.get("id"))
    request_id = text(record.get("requestId"))
    if message_id and request_id:
        return f"{message_id}:{request_id}"
    if message_id:
        return f"msg:{message_id}"
    uuid = text(record.get("uuid"))
    return f"uuid:{uuid}" if uuid else None


def _larger(kept: Turn, other: Turn) -> Turn:
    return replace(
        kept,
        **{
            name: max(getattr(kept, name), getattr(other, name))
            for name, _ in _FIELDS
        },
    )


def _count(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0
