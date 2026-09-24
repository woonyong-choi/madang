"""Agent runners: one fresh CLI subprocess per run, normalized to ``RunEvent``."""

from __future__ import annotations

from pathlib import Path

from madang.config import Config
from madang.runners.base import CliRunner, Runner, RunEvent, RunResult, Usage
from madang.runners.claude import ClaudeRunner
from madang.runners.codex import CodexRunner

RUNNERS: dict[str, type[CliRunner]] = {"claude": ClaudeRunner, "codex": CodexRunner}


def make_runner(name: str, config: Config, *, core_url: str | None = None) -> CliRunner:
    """Build the runner ``name`` from ``config.runners`` (runners.yaml)."""
    if name not in RUNNERS:
        raise ValueError(f"unknown runner {name!r}; expected one of {sorted(RUNNERS)}")
    if name not in config.runners:
        raise ValueError(f"runner {name!r} is not configured in runners.yaml")
    return RUNNERS[name](config.runners[name], home=Path(config.home), core_url=core_url)


__all__ = [
    "RUNNERS",
    "ClaudeRunner",
    "CliRunner",
    "CodexRunner",
    "RunEvent",
    "RunResult",
    "Runner",
    "Usage",
    "make_runner",
]
