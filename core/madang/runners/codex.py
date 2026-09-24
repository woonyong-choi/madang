"""Codex CLI adapter: ``codex exec --json``.

The app home can be made writable for the agent by adding
``["--add-dir", "{home}"]`` to the codex args in runners.yaml.
"""

from __future__ import annotations

from typing import Any

from madang.runners.base import CliRunner, RunEvent, Usage, summarize

_RETRY_PREFIX = "Reconnecting..."


class CodexStreamParser:
    """Maps ``thread.*``/``turn.*``/``item.*``/``error`` lines to run events."""

    def __init__(self) -> None:
        self.final_text = ""
        self.usage: Usage | None = None
        self.error: str | None = None
        self.finished = False
        self._started: set[str] = set()

    def feed(self, obj: dict[str, Any]) -> list[RunEvent]:
        """Returns the events for one decoded JSON line."""
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
            # Transport retries are reported as errors but the turn goes on.
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
    """Runs the Codex CLI."""

    name = "codex"

    def new_parser(self) -> CodexStreamParser:
        """Returns a fresh codex stream parser."""
        return CodexStreamParser()
