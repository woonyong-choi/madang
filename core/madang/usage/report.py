"""응답 하나(``Turn``)의 목록을 도구별 합계와 사용량 창으로 묶는다.

창의 길이(5시간 300분, 주간 10080분)와 80% 경고 기준은 Orca(MIT)의
``src/main/rate-limits/codex-rate-limit-window-classification.ts``와
``src/renderer/src/components/status-bar/usage-roster-formatting.ts``에서
옮겼다. Orca는 창의 사용 비율을 구독 서버(인증 필요)에서 받는다. 우리는
인증 정보를 읽지 않고 플랜별 토큰 한도 표도 없으므로 한도와 비율을
비워 둔다(짐작하지 않는다). 창은 지금에서 거슬러 올라간 구간이다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

# 창 이름과 길이(분).
WINDOWS = (("5h", 300), ("week", 10080))
# 사용 비율이 이 값(%) 이상이면 경고한다.
WARN_PERCENT = 80.0
_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)


@dataclass(frozen=True)
class Turn:
    """응답 하나의 토큰 사용.

    ``input_tokens``는 캐시에서 읽지 않은 입력만 센다.
    """

    timestamp: datetime
    session: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def tokens(self) -> int:
        """네 가지 토큰의 합."""
        return sum(getattr(self, name) for name in _FIELDS)


@dataclass
class _Totals:
    messages: int = 0
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, turn: Turn) -> None:
        self.messages += 1
        for name in _FIELDS:
            self.counts[name] += getattr(turn, name)

    def to_dict(self) -> dict[str, int]:
        return {
            "messages": self.messages,
            **{name: self.counts[name] for name in _FIELDS},
        }


def earliest_start(since: date, now: datetime) -> datetime:
    """합계와 창을 모두 채우려면 읽어야 하는 가장 이른 시각."""
    day_start = datetime.combine(since, datetime.min.time()).astimezone()
    longest = max(minutes for _, minutes in WINDOWS)
    return min(day_start, now - timedelta(minutes=longest))


def summarize(
    tool: str,
    available: bool,
    turns: Iterable[Turn],
    since: date,
    now: datetime,
) -> dict[str, Any]:
    """``ToolUsage`` 형태: 기간 합계, 세션 수, 모델별·날짜별 합계, 창.

    Args:
        tool: 도구 이름.
        available: 사용 기록 폴더가 있는지.
        turns: 응답 목록. 기간 밖의 것도 섞여 있어도 된다.
        since: 합계를 셀 첫날(로컬 날짜, 그날 포함).
        now: 창의 끝 시각.
    """
    turns = list(turns)
    total, models, days = _Totals(), defaultdict(_Totals), defaultdict(_Totals)
    sessions: set[str] = set()
    for turn in turns:
        day = turn.timestamp.astimezone().date()
        if day < since:
            continue
        total.add(turn)
        models[turn.model].add(turn)
        days[day.isoformat()].add(turn)
        sessions.add(turn.session)
    windows = [_window(name, minutes, turns, now) for name, minutes in WINDOWS]
    return {
        "tool": tool,
        "available": available,
        "sessions": len(sessions - {""}),
        **total.to_dict(),
        "models": [
            {"model": name, **models[name].to_dict()} for name in sorted(models)
        ],
        "days": [{"date": day, **days[day].to_dict()} for day in sorted(days)],
        "windows": windows,
        "warn": any(window["warn"] for window in windows),
    }


def _window(
    name: str, minutes: int, turns: list[Turn], now: datetime
) -> dict[str, Any]:
    start = now - timedelta(minutes=minutes)
    # 끝은 초 단위로 자른 확인 시각이므로 그 뒤 기록도 창에 넣는다.
    used = sum(turn.tokens for turn in turns if turn.timestamp > start)
    limit = None  # 플랜별 토큰 한도의 근거가 없다.
    percent = percent_of(used, limit)
    return {
        "name": name,
        "start": start,
        "end": now,
        "used_tokens": used,
        "limit_tokens": limit,
        "percent": percent,
        "warn": warns(percent),
    }


def percent_of(used: int, limit: int | None) -> float | None:
    """한도 대비 사용 비율(0~100). 한도를 모르면 ``None``."""
    if not limit:
        return None
    return min(100.0, max(0.0, used * 100 / limit))


def warns(percent: float | None) -> bool:
    """사용 비율이 경고 기준 이상인지. 비율을 모르면 경고하지 않는다."""
    return percent is not None and percent >= WARN_PERCENT
