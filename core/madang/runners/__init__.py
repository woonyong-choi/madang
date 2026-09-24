"""Agent runners: one fresh CLI subprocess per run, normalized to events."""

from __future__ import annotations

from pathlib import Path

from madang.config import Config
from madang.runners.base import CliRunner, RunEvent, Runner, RunResult, Usage
from madang.runners.claude import ClaudeRunner
from madang.runners.codex import CodexRunner

RUNNERS: dict[str, type[CliRunner]] = {
    "claude": ClaudeRunner,
    "codex": CodexRunner,
}


def make_runner(
    name: str, config: Config, *, core_url: str | None = None
) -> CliRunner:
    """Builds the runner ``name`` from ``config.runners`` (runners.yaml).

    Args:
        name: The runner name, a key of ``RUNNERS``.
        config: The loaded app home configuration.
        core_url: The core API URL passed to the agent, if any.

    Returns:
        The runner.

    Raises:
        ValueError: The runner is unknown or not configured.
    """
    if name not in RUNNERS:
        raise ValueError(
            f"unknown runner {name!r}; expected one of {sorted(RUNNERS)}"
        )
    if name not in config.runners:
        raise ValueError(f"runner {name!r} is not configured in runners.yaml")
    return RUNNERS[name](
        config.runners[name], home=Path(config.home), core_url=core_url
    )


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
