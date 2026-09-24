"""구독 도구의 사용 기록(대화 기록 파일)에서 토큰 사용과 사용량 창을 센다."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from madang.usage import claude, codex
from madang.usage.report import earliest_start, summarize

DEFAULT_DAYS = 7


def tool_usages(
    claude_dir: Path, codex_dir: Path, since: date, now: datetime
) -> list[dict[str, Any]]:
    """도구별 ``ToolUsage``: Claude Code, Codex 순.

    Args:
        claude_dir: Claude Code 폴더(보통 ``~/.claude``).
        codex_dir: Codex 폴더(보통 ``~/.codex``).
        since: 합계를 셀 첫날(로컬 날짜, 그날 포함).
        now: 지금. 창의 끝이다.
    """
    start = earliest_start(since, now)
    return [
        summarize(
            reader.TOOL,
            reader.available(folder),
            reader.read_turns(folder, start),
            since,
            now,
        )
        for reader, folder in ((claude, claude_dir), (codex, codex_dir))
    ]
