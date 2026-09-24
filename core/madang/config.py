"""App home location and config file loading."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

HOME_ENV = "MADANG_HOME"
DEFAULT_HOME = "~/.madang"
CONFIG_DIR = "config"
CONFIG_FILES = ("madang.yaml", "routes.yaml", "runners.yaml")


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


# madang.yaml


class CoreSettings(_Model):
    port: int = 7470
    bind: str = "127.0.0.1"


class AgentSettings(_Model):
    claude_settings: str = "~/.claude/settings.json"
    codex_config: str = "~/.codex/config.toml"


class Limits(_Model):
    state_tokens: int = 2000
    block_input_tokens: int = 4000
    run_timeout_minutes: dict[str, int] = Field(
        default_factory=lambda: {"design": 30, "build": 20, "small": 5, "review": 10, "explore": 5}
    )


class UiSettings(_Model):
    language: str = "ko"


class MadangConfig(_Model):
    home_remote: str | None = None
    core: CoreSettings = Field(default_factory=CoreSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    limits: Limits = Field(default_factory=Limits)
    ui: UiSettings = Field(default_factory=UiSettings)


# routes.yaml


class Tier(_Model):
    runner: str
    model: str
    effort: str | None = None


class RouteLimits(_Model):
    max_runs_per_message: int = 6
    blocked_after_failures: int = 2


class DeciderSettings(_Model):
    chain: list[str] = Field(default_factory=lambda: ["rules", "light_model"])
    min_confidence: float = 0.7


class RoutesConfig(_Model):
    kinds: list[str]
    default_kind: str
    prefix_override: bool = True
    rules: dict[str, list[str]] = Field(default_factory=dict)
    tiers: dict[str, list[Tier]] = Field(default_factory=dict)
    limits: RouteLimits = Field(default_factory=RouteLimits)
    decider: DeciderSettings = Field(default_factory=DeciderSettings)


# runners.yaml


class RunnerSpec(_Model):
    bin: str
    args: list[str] = Field(default_factory=list)
    auth: str = "subscription"
    cache_ttl: str | None = None


class Config(BaseModel):
    home: Path
    madang: MadangConfig
    routes: RoutesConfig
    runners: dict[str, RunnerSpec]


def resolve_home(home: str | os.PathLike[str] | None = None) -> Path:
    """Return the app home: explicit argument, then MADANG_HOME, then ~/.madang."""
    raw = home if home is not None else os.environ.get(HOME_ENV) or DEFAULT_HOME
    return Path(raw).expanduser().resolve()


def default_text(name: str) -> str:
    """Read a bundled default file from madang/defaults."""
    return resources.files("madang").joinpath("defaults", name).read_text(encoding="utf-8")


def _read_yaml(path: Path, name: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.is_file() else default_text(name)
    data = yaml.safe_load(text)
    return data or {}


def load_config(home: str | os.PathLike[str] | None = None) -> Config:
    """Load config/*.yaml from the app home, falling back to bundled defaults."""
    root = resolve_home(home)
    cfg = root / CONFIG_DIR
    return Config(
        home=root,
        madang=MadangConfig.model_validate(_read_yaml(cfg / "madang.yaml", "madang.yaml")),
        routes=RoutesConfig.model_validate(_read_yaml(cfg / "routes.yaml", "routes.yaml")),
        runners={
            name: RunnerSpec.model_validate(spec)
            for name, spec in _read_yaml(cfg / "runners.yaml", "runners.yaml").items()
        },
    )
