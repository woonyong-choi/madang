"""Claude Code 어댑터: ``claude -p --output-format stream-json --verbose``."""

from __future__ import annotations

from typing import Any

from madang.runners.base import CliRunner, RunEvent, Usage, summarize

# 성공 결과가 ``file_path`` 파일을 썼다는 뜻인 도구.
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
# 도구 이름별로 호출을 가장 잘 설명하는 입력 키.
_SUMMARY_KEYS = {
    "Bash": "command",
    "Read": "file_path",
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
    "Glob": "pattern",
    "Grep": "pattern",
    "WebFetch": "url",
    "WebSearch": "query",
    "Task": "description",
}


class ClaudeStreamParser:
    """``system``/``assistant``/``user``/``result`` 줄을 이벤트로 옮긴다."""

    def __init__(self) -> None:
        self.final_text = ""
        self.usage: Usage | None = None
        self.error: str | None = None
        self.finished = False
        self._pending_writes: dict[str, str] = {}

    def feed(self, obj: dict[str, Any]) -> list[RunEvent]:
        """디코딩된 JSON 한 줄에 대한 이벤트를 반환한다."""
        kind = obj.get("type")
        if kind == "assistant":
            return self._assistant(obj)
        if kind == "user":
            return self._user(obj)
        if kind == "result":
            return self._result(obj)
        return []

    def _assistant(self, obj: dict[str, Any]) -> list[RunEvent]:
        events: list[RunEvent] = []
        for part in _content(obj):
            ptype = part.get("type")
            if ptype == "text" and part.get("text"):
                events.append(RunEvent("text", text=part["text"]))
            elif ptype == "tool_use":
                name = str(part.get("name") or "tool")
                args = (
                    part.get("input")
                    if isinstance(part.get("input"), dict)
                    else {}
                )
                key = _SUMMARY_KEYS.get(name)
                summary = summarize(args[key] if key and key in args else args)
                events.append(RunEvent("tool_call", name=name, summary=summary))
                path = args.get("file_path") or args.get("notebook_path")
                if name in _WRITE_TOOLS and path and part.get("id"):
                    self._pending_writes[str(part["id"])] = str(path)
        return events

    def _user(self, obj: dict[str, Any]) -> list[RunEvent]:
        events: list[RunEvent] = []
        for part in _content(obj):
            if part.get("type") != "tool_result":
                continue
            failed = bool(part.get("is_error"))
            summary = summarize(_result_text(part.get("content")))
            events.append(
                RunEvent(
                    "tool_result",
                    summary=("error: " if failed else "") + summary,
                )
            )
            path = self._pending_writes.pop(str(part.get("tool_use_id")), None)
            if path and not failed:
                events.append(RunEvent("file_changed", path=path))
        return events

    def _result(self, obj: dict[str, Any]) -> list[RunEvent]:
        self.finished = True
        events: list[RunEvent] = []
        raw = obj.get("usage")
        if isinstance(raw, dict):
            self.usage = _usage(raw)
            events.append(RunEvent("usage", usage=self.usage))
        text = obj.get("result")
        self.final_text = text if isinstance(text, str) else ""
        if obj.get("is_error") or obj.get("subtype") != "success":
            errors = obj.get("errors")
            detail = self.final_text or (
                summarize(errors, 500) if errors else ""
            )
            self.error = detail or f"claude run failed ({obj.get('subtype')})"
            events.append(RunEvent("error", message=self.error))
        return events


def _content(obj: dict[str, Any]) -> list[dict[str, Any]]:
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return (
        [p for p in content if isinstance(p, dict)]
        if isinstance(content, list)
        else []
    )


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return " ".join(t for t in texts if t)
    return ""


def _usage(raw: dict[str, Any]) -> Usage:
    fresh = int(raw.get("input_tokens") or 0)
    created = int(raw.get("cache_creation_input_tokens") or 0)
    read = int(raw.get("cache_read_input_tokens") or 0)
    return Usage(
        input=fresh + created + read,
        cached=read,
        output=int(raw.get("output_tokens") or 0),
    )


class ClaudeRunner(CliRunner):
    """Claude Code를 실행한다."""

    name = "claude"

    def new_parser(self) -> ClaudeStreamParser:
        """새 claude 스트림 파서를 반환한다."""
        return ClaudeStreamParser()
