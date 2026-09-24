"""에이전트 러너: 실행마다 새 CLI 서브프로세스를 띄우고 이벤트로 정규화한다."""

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
    """``config.runners``(config.yaml의 runners 절)에서 러너 ``name``을 만든다.

    Args:
        name: 러너 이름. ``RUNNERS``의 키.
        config: 로드된 앱 홈 설정.
        core_url: 에이전트에 넘길 core API URL. 없을 수 있다.

    Returns:
        러너.

    Raises:
        ValueError: 러너를 모르거나 설정되지 않았다.
    """
    if name not in RUNNERS:
        raise ValueError(
            f"unknown runner {name!r}; expected one of {sorted(RUNNERS)}"
        )
    if name not in config.runners:
        raise ValueError(f"runner {name!r} is not in config.yaml runners")
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
