"""앱 홈(전역 설정 폴더) 위치와 설정 파일 로딩."""

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
# core가 고른 포트를 적어 두는 앱 홈 파일
PORT_FILE = "core.port"
CONFIG_FILES = ("madang.yaml", "routes.yaml", "runners.yaml")


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


# madang.yaml


class CoreSettings(_Model):
    """코어 API가 대기하는 주소."""

    port: int = 7470
    bind: str = "127.0.0.1"


class AgentSettings(_Model):
    """에이전트 도구 자체 설정 파일의 경로."""

    claude_settings: str = "~/.claude/settings.json"
    codex_config: str = "~/.codex/config.toml"


class Limits(_Model):
    """페이지와 실행의 크기·시간 제한."""

    state_tokens: int = 2000
    block_input_tokens: int = 4000
    run_timeout_minutes: dict[str, int] = Field(
        default_factory=lambda: {
            "design": 30,
            "build": 20,
            "small": 5,
            "review": 10,
            "explore": 5,
        }
    )


class UiSettings(_Model):
    """데스크톱 앱 환경설정."""

    language: str = "ko"


class ProjectEntry(_Model):
    """등록한 프로젝트 하나. 표시 설정도 여기에 둔다."""

    id: str
    path: str
    title: str | None = None
    parent: str | None = None
    icon: str | None = None
    color: str | None = None
    sort: str | None = None


class MadangConfig(_Model):
    """``config/madang.yaml``의 전역 설정."""

    commit_records: bool = False
    projects: list[ProjectEntry] = Field(default_factory=list)
    core: CoreSettings = Field(default_factory=CoreSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    limits: Limits = Field(default_factory=Limits)
    ui: UiSettings = Field(default_factory=UiSettings)


# routes.yaml


class Tier(_Model):
    """실행 종류별 러너와 모델 선택 하나."""

    runner: str
    model: str
    effort: str | None = None


class RouteLimits(_Model):
    """메시지 하나가 시작할 수 있는 실행 수의 제한."""

    max_runs_per_message: int = 6
    blocked_after_failures: int = 2


class DeciderSettings(_Model):
    """종류를 고르는 판정기와 필요한 확신도."""

    chain: list[str] = Field(default_factory=lambda: ["rules", "light_model"])
    min_confidence: float = 0.7


class RoutesConfig(_Model):
    """``config/routes.yaml``의 라우팅 표."""

    kinds: list[str]
    default_kind: str
    prefix_override: bool = True
    rules: dict[str, list[str]] = Field(default_factory=dict)
    tiers: dict[str, list[Tier]] = Field(default_factory=dict)
    limits: RouteLimits = Field(default_factory=RouteLimits)
    decider: DeciderSettings = Field(default_factory=DeciderSettings)


# runners.yaml


class RunnerSpec(_Model):
    """``config/runners.yaml``의 에이전트 CLI 하나를 시작하는 방법."""

    bin: str
    args: list[str] = Field(default_factory=list)
    auth: str = "subscription"
    cache_ttl: str | None = None


class Config(BaseModel):
    """앱 홈 ``config/`` 폴더에서 읽은 모든 설정."""

    home: Path
    madang: MadangConfig
    routes: RoutesConfig
    runners: dict[str, RunnerSpec]


def resolve_home(home: str | os.PathLike[str] | None = None) -> Path:
    """앱 홈 폴더를 반환한다.

    Args:
        home: 명시한 경로. ``MADANG_HOME``보다, ``MADANG_HOME``은
            ``~/.madang``보다 우선한다.

    Returns:
        앱 홈의 절대 경로.
    """
    raw = home if home is not None else os.environ.get(HOME_ENV) or DEFAULT_HOME
    return Path(raw).expanduser().resolve()


def default_text(name: str) -> str:
    """번들된 기본 파일의 텍스트를 반환한다.

    Args:
        name: ``madang/defaults``의 파일 이름.

    Returns:
        파일 내용.
    """
    return (
        resources.files("madang")
        .joinpath("defaults", name)
        .read_text(encoding="utf-8")
    )


def _read_yaml(path: Path, name: str) -> dict[str, Any]:
    text = (
        path.read_text(encoding="utf-8")
        if path.is_file()
        else default_text(name)
    )
    data = yaml.safe_load(text)
    return data or {}


def load_config(home: str | os.PathLike[str] | None = None) -> Config:
    """앱 홈의 ``config/*.yaml``을 읽는다.

    없는 파일은 번들된 기본값으로 대신한다.

    Args:
        home: 앱 홈. ``resolve_home``과 같이 해석한다.

    Returns:
        읽은 설정.

    Raises:
        OSError: 설정 파일을 읽을 수 없는 경우.
        yaml.YAMLError: 설정 파일이 올바른 YAML이 아닌 경우.
        pydantic.ValidationError: 설정 파일이 스키마와 맞지 않는 경우.
    """
    root = resolve_home(home)
    cfg = root / CONFIG_DIR
    return Config(
        home=root,
        madang=MadangConfig.model_validate(
            _read_yaml(cfg / "madang.yaml", "madang.yaml")
        ),
        routes=RoutesConfig.model_validate(
            _read_yaml(cfg / "routes.yaml", "routes.yaml")
        ),
        runners={
            name: RunnerSpec.model_validate(spec)
            for name, spec in _read_yaml(
                cfg / "runners.yaml", "runners.yaml"
            ).items()
        },
    )
