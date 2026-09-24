import json

from conftest import STREAMS

from madang.runners.base import RunEvent, Usage
from madang.runners.claude import ClaudeStreamParser
from madang.runners.codex import CodexStreamParser


def replay(parser, name: str) -> list[RunEvent]:
    events: list[RunEvent] = []
    for line in (STREAMS / name).read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.extend(parser.feed(json.loads(line)))
    return events


def types(events: list[RunEvent]) -> list[str]:
    return [e.type for e in events]


# claude


def test_claude_ok() -> None:
    parser = ClaudeStreamParser()
    events = replay(parser, "claude-ok.jsonl")

    assert types(events) == ["text", "usage"]
    assert events[0].text == "ok"
    assert parser.finished and parser.error is None
    assert parser.final_text == "ok"
    # input = 새 입력 + 캐시 생성 + 캐시 읽기, cached = 캐시 읽기
    assert parser.usage == Usage(
        input=10 + 9469 + 13689, cached=13689, output=347
    )
    assert events[1].usage == parser.usage


def test_claude_tools() -> None:
    parser = ClaudeStreamParser()
    events = replay(parser, "claude-tools.jsonl")

    assert types(events) == [
        "tool_call",
        "tool_result",
        "file_changed",
        "tool_call",
        "tool_result",
        "text",
        "usage",
    ]
    write, write_result, changed, bash, bash_result, text, _ = events
    assert (write.name, write.summary) == ("Write", "/work/project/hello.txt")
    assert write_result.summary.startswith("File created successfully")
    assert changed.path == "/work/project/hello.txt"
    assert (bash.name, bash.summary) == ("Bash", "ls")
    assert bash_result.summary == "hello.txt"
    assert text.text == "Done."
    assert parser.final_text == "Done."
    assert parser.usage is not None and parser.usage.output > 0


def test_claude_error_result() -> None:
    parser = ClaudeStreamParser()
    events = replay(parser, "claude-error.jsonl")

    assert types(events)[-1] == "error"
    assert parser.finished
    assert parser.error is not None and "claude-nope-9" in parser.error
    assert parser.usage == Usage()


def test_claude_failed_write_is_not_a_change() -> None:
    parser = ClaudeStreamParser()
    parser.feed(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Edit",
                        "input": {"file_path": "a.txt"},
                    },
                ]
            },
        }
    )
    events = parser.feed(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "is_error": True,
                        "content": [
                            {"type": "text", "text": "String not found"}
                        ],
                    },
                ]
            },
        }
    )
    assert types(events) == ["tool_result"]
    assert events[0].summary == "error: String not found"


def test_claude_ignores_unknown_lines() -> None:
    parser = ClaudeStreamParser()
    assert parser.feed({"type": "rate_limit_event"}) == []
    assert parser.feed({"type": "system", "subtype": "init"}) == []
    assert not parser.finished


# codex


def test_codex_ok() -> None:
    parser = CodexStreamParser()
    events = replay(parser, "codex-ok.jsonl")

    assert types(events) == ["text", "usage"]
    assert parser.final_text == "ok"
    assert parser.finished and parser.error is None
    assert parser.usage == Usage(input=3712, cached=2048, output=18)


def test_codex_tools() -> None:
    parser = CodexStreamParser()
    events = replay(parser, "codex-tools.jsonl")

    assert types(events) == [
        "tool_call",
        "tool_result",
        "text",
        "file_changed",
        "file_changed",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "text",
        "usage",
    ]
    assert (events[0].name, events[0].summary) == ("shell", "bash -lc ls")
    assert events[1].summary == "exit 0: README.md src"
    assert [e.path for e in events if e.type == "file_changed"] == [
        "/work/project/hello.txt",
        "/work/project/README.md",
    ]
    assert events[6].summary.startswith("exit 1: cat: missing.txt")
    assert (events[7].name, events[7].summary) == (
        "docs.search",
        '{"query":"runner"}',
    )
    # 전송 재시도 안내는 오류가 아니다
    assert parser.error is None
    assert parser.final_text == "done"
    assert parser.usage == Usage(input=15230, cached=11904, output=402)


def test_codex_error() -> None:
    parser = CodexStreamParser()
    events = replay(parser, "codex-error.jsonl")

    errors = [e for e in events if e.type == "error"]
    # 재시도는 건너뛰고 최종 오류와 turn.failed만 남는다
    assert len(errors) == 2
    assert all("401 Unauthorized" in (e.message or "") for e in errors)
    assert not parser.finished
    assert parser.error is not None and "401" in parser.error
    assert parser.usage is None


def test_codex_tool_call_without_start() -> None:
    parser = CodexStreamParser()
    events = parser.feed(
        {
            "type": "item.completed",
            "item": {
                "id": "x",
                "type": "command_execution",
                "command": "true",
                "aggregated_output": "",
                "exit_code": 0,
                "status": "completed",
            },
        }
    )
    assert types(events) == ["tool_call", "tool_result"]
    assert events[1].summary == "exit 0"


def test_fixtures_have_no_personal_paths() -> None:
    for path in STREAMS.glob("*.jsonl"):
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text, path.name
        assert "/private/tmp" not in text, path.name


def test_event_to_dict_drops_unset_fields() -> None:
    event = RunEvent("tool_call", name="Bash", summary="ls")
    assert event.to_dict() == {
        "type": "tool_call",
        "name": "Bash",
        "summary": "ls",
    }
    assert RunEvent("usage", usage=Usage(1, 0, 2)).to_dict() == {
        "type": "usage",
        "usage": {"input": 1, "cached": 0, "output": 2},
    }
