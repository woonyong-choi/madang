"""Codex CLI 어댑터: ``codex exec --json``.

config.yaml runners 절의 codex args에 ``["--add-dir", "{home}"]``를 추가하면
에이전트가 앱 홈에 쓸 수 있다.
"""

from __future__ import annotations

from typing import Any

from madang.runners.base import CliRunner, RunEvent, Usage, summarize

_RETRY_PREFIX = "Reconnecting..."


class CodexStreamParser:
    """``thread.*``/``turn.*``/``item.*``/``error`` 줄을 이벤트로 옮긴다."""

    def __init__(self) -> None:
        self.final_text = ""
        self.usage: Usage | None = None
        self.error: str | None = None
        self.finished = False
        self._started: set[str] = set()

    def feed(self, obj: dict[str, Any]) -> list[RunEvent]:
        """디코딩된 JSON 한 줄에 대한 이벤트를 반환한다."""
        kind = obj.get("type")
        if kind == "item.started":
            return self._item_started(_item(obj))
        if kind == "item.completed":
            return self._item_completed(_item(obj))
        if kind == "turn.completed":
            return self._turn_completed(obj)
        if kind == "turn.failed":
            err = obj.get("error")
            return self._fail(
                err.get("message") if isinstance(err, dict) else err
            )
        if kind == "error":
            message = obj.get("message")
            # 전송 재시도는 오류로 보고되지만 턴은 계속된다.
            if isinstance(message, str) and message.startswith(_RETRY_PREFIX):
                return []
            return self._fail(message)
        return []

    def _item_started(self, item: dict[str, Any]) -> list[RunEvent]:
        call = _tool_call(item)
        if call is None:
            return []
        self._started.add(str(item.get("id")))
        return [call]

    def _item_completed(self, item: dict[str, Any]) -> list[RunEvent]:
        itype = item.get("type")
        if itype == "agent_message":
            text = item.get("text")
            if not isinstance(text, str) or not text:
                return []
            self.final_text = text
            return [RunEvent("text", text=text)]
        if itype == "file_change":
            changes = (
                item.get("changes")
                if isinstance(item.get("changes"), list)
                else []
            )
            if item.get("status") == "failed":
                return []
            return [
                RunEvent("file_changed", path=str(c["path"]))
                for c in changes
                if isinstance(c, dict) and c.get("path")
            ]

        events: list[RunEvent] = []
        call = _tool_call(item)
        if call is None:
            return events
        if str(item.get("id")) not in self._started:
            events.append(call)
        events.append(RunEvent("tool_result", summary=_tool_result(item)))
        return events

    def _turn_completed(self, obj: dict[str, Any]) -> list[RunEvent]:
        self.finished = True
        raw = obj.get("usage")
        if not isinstance(raw, dict):
            return []
        usage = Usage(
            input=int(raw.get("input_tokens") or 0),
            cached=int(raw.get("cached_input_tokens") or 0),
            output=int(raw.get("output_tokens") or 0),
        )
        self.usage = usage if self.usage is None else self.usage + usage
        return [RunEvent("usage", usage=usage)]

    def _fail(self, message: Any) -> list[RunEvent]:
        text = summarize(message, 500) if message else "codex run failed"
        self.error = text
        return [RunEvent("error", message=text)]


def _item(obj: dict[str, Any]) -> dict[str, Any]:
    item = obj.get("item")
    return item if isinstance(item, dict) else {}


def _tool_call(item: dict[str, Any]) -> RunEvent | None:
    itype = item.get("type")
    if itype == "command_execution":
        return RunEvent(
            "tool_call",
            name="shell",
            summary=summarize(item.get("command", "")),
        )
    if itype == "mcp_tool_call":
        name = ".".join(
            str(p) for p in (item.get("server"), item.get("tool")) if p
        )
        return RunEvent(
            "tool_call",
            name=name or "mcp",
            summary=summarize(item.get("arguments") or ""),
        )
    if itype == "web_search":
        return RunEvent(
            "tool_call",
            name="web_search",
            summary=summarize(item.get("query", "")),
        )
    return None


def _tool_result(item: dict[str, Any]) -> str:
    if item.get("type") == "command_execution":
        output = summarize(item.get("aggregated_output") or "")
        head = f"exit {item.get('exit_code')}"
        return f"{head}: {output}" if output else head
    status = str(item.get("status") or "completed")
    err = item.get("error")
    if isinstance(err, dict) and err.get("message"):
        return f"{status}: {summarize(err['message'])}"
    return status


class CodexRunner(CliRunner):
    """Codex CLI를 실행한다."""

    name = "codex"

    def new_parser(self) -> CodexStreamParser:
        """새 codex 스트림 파서를 반환한다."""
        return CodexStreamParser()
