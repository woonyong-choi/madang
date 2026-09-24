"""Codex가 남긴 세션 기록(rollout)에서 응답별 토큰 사용을 읽는다.

Orca(MIT)의 ``src/main/codex-usage/codex-usage-record-parser.ts``와
``codex-usage-token-delta.ts``를 옮겼다. ``~/.codex/sessions`` 아래
``*.jsonl``의 ``token_count`` 이벤트만 읽는다. 인증·설정 파일은 읽지
않는다. Codex의 누계(``total_token_usage``)는 압축·재개 뒤 바뀌는
스냅숏이므로 이번 응답분(``last_token_usage``)을 세고, 누계는 기준으로만
쓴다. 포크·재개로 복사된 이벤트는 시각과 사용량 값으로 한 번만 센다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from madang.usage.records import json_lines, jsonl_files, parse_time, text
from madang.usage.report import Turn

TOOL = "codex"
SESSIONS_DIR = "sessions"


@dataclass(frozen=True)
class RawUsage:
    """Codex 사용량 값. ``input``은 캐시 입력을 포함한다."""

    input: int = 0
    cached_input: int = 0
    output: int = 0
    reasoning_output: int = 0
    total: int = 0

    @property
    def parts(self) -> tuple[int, int, int, int]:
        """합계를 뺀 네 값. 비교와 크기는 이것으로 한다."""
        return (
            self.input,
            self.cached_input,
            self.output,
            self.reasoning_output,
        )

    def values(self) -> tuple[int, ...]:
        """다섯 값 전부."""
        return (*self.parts, self.total)

    def minus(self, other: RawUsage) -> RawUsage:
        """항목별 차이. 음수는 0으로 둔다."""
        pairs = zip(self.values(), other.values(), strict=True)
        return RawUsage(*(max(a - b, 0) for a, b in pairs))

    def plus(self, other: RawUsage) -> RawUsage:
        """항목별 합."""
        pairs = zip(self.values(), other.values(), strict=True)
        return RawUsage(*(a + b for a, b in pairs))

    def grew_from(self, previous: RawUsage) -> bool:
        """네 값 모두 줄지 않았는지."""
        pairs = zip(self.parts, previous.parts, strict=True)
        return all(a >= b for a, b in pairs)


def normalize(value: Any) -> RawUsage | None:
    """``*_token_usage`` 객체를 ``RawUsage``로. 객체가 아니면 ``None``."""
    if not isinstance(value, dict):
        return None
    input_tokens = _number(value.get("input_tokens"))
    output = _number(value.get("output_tokens"))
    total = _number(value.get("total_tokens"))
    cached = value.get("cached_input_tokens")
    if cached is None:
        cached = value.get("cache_read_input_tokens")
    return RawUsage(
        input=input_tokens,
        cached_input=_number(cached),
        output=output,
        reasoning_output=_number(value.get("reasoning_output_tokens")),
        # 예전 기록은 합계가 없다. 추론 토큰은 출력에 들어 있어 더하지 않는다.
        total=total if total > 0 else input_tokens + output,
    )


def resolve_delta(
    total: RawUsage | None, last: RawUsage | None, previous: RawUsage | None
) -> tuple[RawUsage | None, RawUsage | None] | None:
    """이번 이벤트의 증가분과 다음 기준 누계.

    Returns:
        ``(증가분, 다음 기준)``. 증가분이 ``None``이면 기준만 바꾼다. 셀 것도
        바꿀 것도 없으면 ``None``.
    """
    if total and last and previous:
        if total.parts == previous.parts:
            return None
        if not total.grew_from(previous) and _stale(total, previous, last):
            return None
        return last, total
    if total and last:
        return last, total
    if total and previous:
        if total.parts == previous.parts:
            return None
        if not total.grew_from(previous):
            return None, total
        return total.minus(previous), total
    if total:
        return total, total
    if last and previous:
        return last, previous.plus(last)
    if last:
        return last, None
    return None


def _stale(current: RawUsage, previous: RawUsage, last: RawUsage) -> bool:
    """누계가 줄었지만 예전 스냅숏이 다시 온 것으로 보이는지."""
    before, now, step = (sum(u.parts) for u in (previous, current, last))
    if before <= 0 or now <= 0 or step <= 0:
        return False
    return now * 100 >= before * 98 or now + step * 2 >= before


@dataclass
class _Context:
    session: str
    model: str | None = None
    previous: RawUsage | None = None


def available(codex_dir: Path) -> bool:
    """세션 기록 폴더가 있는지."""
    return (codex_dir / SESSIONS_DIR).is_dir()


def read_turns(codex_dir: Path, start: datetime) -> list[Turn]:
    """``start`` 뒤에 고친 세션 파일의 응답들.

    Args:
        codex_dir: Codex 폴더(보통 ``~/.codex``).
        start: 이보다 먼저 고친 파일은 읽지 않는다.
    """
    turns: dict[str, Turn] = {}
    for path in jsonl_files([codex_dir / SESSIONS_DIR], start):
        context = _Context(session=path.stem)
        for record in json_lines(path):
            found = _parse_record(record, context)
            if found is not None:
                key, turn = found
                turns.setdefault(key, turn)
    return list(turns.values())


def _parse_record(
    record: dict[str, Any], context: _Context
) -> tuple[str, Turn] | None:
    """기록 한 줄을 읽어 문맥을 갱신하고, 토큰 이벤트면 ``(열쇠, Turn)``."""
    kind, payload = record.get("type"), record.get("payload")
    if not isinstance(payload, dict):
        return None
    if kind == "session_meta":
        context.session = text(payload.get("id")) or context.session
        return None
    if kind == "turn_context":
        context.model = _model(payload) or context.model
        return None
    stamp = parse_time(record.get("timestamp"))
    if kind != "event_msg" or payload.get("type") != "token_count" or not stamp:
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        # 사용량 없이 요율 제한만 알리는 이벤트다.
        return None
    total = normalize(info.get("total_token_usage"))
    last = normalize(info.get("last_token_usage"))
    resolved = resolve_delta(total, last, context.previous)
    if resolved is None:
        return None
    delta, following = resolved
    if delta is None:
        context.previous = following
        return None
    cached = min(delta.cached_input, delta.input)
    if not any(delta.values()):
        return None
    context.previous = following
    key = "|".join(
        [
            str(record["timestamp"]),
            *(_tuple(usage) for usage in (total, last)),
        ]
    )
    turn = Turn(
        timestamp=stamp,
        session=context.session,
        model=_model(payload) or context.model or "unknown",
        input_tokens=delta.input - cached,
        output_tokens=delta.output,
        cache_read_tokens=cached,
    )
    return key, turn


def _model(payload: dict[str, Any]) -> str | None:
    """``model``·``model_name``를 직접, ``info``, ``metadata`` 순으로 찾는다."""
    direct = text(payload.get("model")) or text(payload.get("model_name"))
    if direct:
        return direct
    info = payload.get("info")
    if isinstance(info, dict):
        found = text(info.get("model")) or text(info.get("model_name"))
        metadata = info.get("metadata")
        if not found and isinstance(metadata, dict):
            found = text(metadata.get("model"))
        if found:
            return found
    metadata = payload.get("metadata")
    return text(metadata.get("model")) if isinstance(metadata, dict) else None


def _tuple(usage: RawUsage | None) -> str:
    return ",".join(map(str, usage.values())) if usage else ""


def _number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return int(value) if math.isfinite(value) else 0
