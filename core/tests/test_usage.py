"""사용량: 가짜 Claude Code·Codex 기록에서 응답별 토큰과 창을 센다."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from madang import usage
from madang.usage import claude, codex
from madang.usage.report import WARN_PERCENT, percent_of, warns

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=30)


def stamp(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def write_lines(path: Path, records: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n")
    return path


def assistant(hours_ago: float, **usage_fields) -> dict:
    return {
        "type": "assistant",
        "sessionId": "s1",
        "requestId": usage_fields.pop("request", "r1"),
        "timestamp": stamp(hours_ago),
        "message": {
            "id": usage_fields.pop("message", "m1"),
            "model": "claude-opus-5-5",
            "usage": usage_fields,
        },
    }


# Claude Code


def test_claude_repeats_keep_the_most_complete_usage(tmp_path: Path) -> None:
    write_lines(
        tmp_path / "projects/-work/s1.jsonl",
        [
            assistant(1, input_tokens=10, output_tokens=1),
            assistant(
                1, input_tokens=10, output_tokens=40
            ),  # 같은 응답, 뒤가 완전
            assistant(2, message="m2", request="", output_tokens=3),
            assistant(3, message="m3", input_tokens=0),  # 토큰 없음
            {"type": "user", "message": {"content": "assistant"}},
            "{broken",
        ],
    )
    turns = claude.read_turns(tmp_path, LONG_AGO)
    assert sorted(t.output_tokens for t in turns) == [3, 40]
    assert claude.available(tmp_path)


def test_claude_reads_transcripts_and_skips_old_files(tmp_path: Path) -> None:
    write_lines(
        tmp_path / "transcripts/t.jsonl",
        [assistant(1, message="t", output_tokens=2)],
    )
    old = write_lines(
        tmp_path / "projects/-old/s.jsonl", [assistant(1, output_tokens=5)]
    )
    ancient = (LONG_AGO - timedelta(days=1)).timestamp()
    os.utime(old, (ancient, ancient))
    turns = claude.read_turns(tmp_path, LONG_AGO)
    assert [t.output_tokens for t in turns] == [2]


def test_claude_is_unavailable_without_history(tmp_path: Path) -> None:
    assert not claude.available(tmp_path)
    assert claude.read_turns(tmp_path, LONG_AGO) == []


# Codex


def token_count(hours_ago: float, total=None, last=None, **payload) -> dict:
    info = {}
    if total is not None:
        info["total_token_usage"] = total
    if last is not None:
        info["last_token_usage"] = last
    return {
        "timestamp": stamp(hours_ago),
        "type": "event_msg",
        "payload": {"type": "token_count", "info": info or None, **payload},
    }


def tokens(inp: int, cached: int, out: int, total: int | None = None) -> dict:
    found = {"input_tokens": inp, "cached_input_tokens": cached}
    found["output_tokens"] = out
    if total is not None:
        found["total_tokens"] = total
    return found


def codex_session(tmp_path: Path, name: str = "rollout-a.jsonl") -> Path:
    return tmp_path / "sessions/2026/09/24" / name


def test_codex_counts_last_usage_and_skips_repeats(tmp_path: Path) -> None:
    records = [
        {"type": "session_meta", "payload": {"id": "sess-1", "cwd": "/w"}},
        {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
        token_count(2, tokens(100, 40, 10), tokens(100, 40, 10)),
        token_count(2, tokens(100, 40, 10), tokens(100, 40, 10)),  # 같은 누계
        token_count(1, tokens(160, 50, 30), tokens(60, 10, 20)),
        token_count(1, None, None, rate_limits={}),  # 요율 제한만
    ]
    write_lines(codex_session(tmp_path), records)
    # 포크로 복사된 같은 이벤트는 다시 세지 않는다.
    write_lines(codex_session(tmp_path, "rollout-b.jsonl"), records)
    turns = codex.read_turns(tmp_path, LONG_AGO)
    assert [
        (t.input_tokens, t.cache_read_tokens, t.output_tokens) for t in turns
    ] == [
        (60, 40, 10),
        (50, 10, 20),
    ]
    assert {t.session for t in turns} == {"sess-1"}
    assert {t.model for t in turns} == {"gpt-6-sol"}


def test_codex_total_only_logs_count_growth(tmp_path: Path) -> None:
    write_lines(
        codex_session(tmp_path),
        [
            token_count(3, tokens(10, 0, 5)),
            token_count(2, tokens(30, 5, 9)),
            token_count(1, tokens(4, 0, 1)),  # 누계가 줄면 기준만 바꾼다
        ],
    )
    turns = codex.read_turns(tmp_path, LONG_AGO)
    assert [
        (t.input_tokens + t.cache_read_tokens, t.output_tokens) for t in turns
    ] == [
        (10, 5),
        (20, 4),
    ]


def test_codex_resolve_delta_ignores_stale_snapshot() -> None:
    previous = codex.normalize(tokens(1000, 0, 100))
    stale = codex.normalize(tokens(990, 0, 100))
    last = codex.normalize(tokens(10, 0, 1))
    assert codex.resolve_delta(stale, last, previous) is None
    assert codex.normalize(tokens(3, 0, 2)).total == 5
    assert codex.normalize("x") is None


# 합계와 창


def test_windows_look_back_from_now(tmp_path: Path) -> None:
    write_lines(
        tmp_path / "projects/-work/s1.jsonl",
        [
            assistant(1, message="a", output_tokens=1),
            assistant(6, message="b", output_tokens=10),
            assistant(24 * 8, message="c", output_tokens=100),
        ],
    )
    for path in (tmp_path / "projects").rglob("*.jsonl"):
        os.utime(path, (NOW.timestamp(), NOW.timestamp()))
    since = (NOW - timedelta(hours=6)).astimezone().date()
    found = usage.tool_usages(tmp_path, tmp_path / "none", since, NOW)
    tool, other = found
    windows = {w["name"]: w for w in tool["windows"]}
    assert windows["5h"]["used_tokens"] == 1
    assert windows["5h"]["start"] == NOW - timedelta(hours=5)
    assert windows["week"]["used_tokens"] == 11
    assert windows["week"]["end"] == NOW
    assert windows["week"]["limit_tokens"] is None
    assert windows["week"]["percent"] is None and tool["warn"] is False
    assert tool["output_tokens"] == 11  # since 날부터의 합계
    assert (other["tool"], other["available"]) == ("codex", False)


@pytest.mark.parametrize(
    ("used", "limit", "percent", "warn"),
    [
        (0, None, None, False),
        (79, 100, 79.0, False),
        (80, 100, 80.0, True),
        (500, 100, 100.0, True),
    ],
)
def test_percent_and_warning(used, limit, percent, warn) -> None:
    assert percent_of(used, limit) == percent
    assert warns(percent) is warn
    assert WARN_PERCENT == 80.0
