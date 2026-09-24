"""앱 홈(전역 설정 폴더) 위치와 설정 파일 로딩.

전역 설정은 앱 홈의 ``config.yaml`` 하나다. 앱 동작 설정, 프로젝트 목록,
라우팅 표(``routes:``), 러너(``runners:``)를 절로 나눠 담는다. 프로젝트
설정은 ``<project>/.madang/config.yaml``이다. 둘 다 앱이 읽는 설정이며
에이전트가 받는 기억(md)과 섞지 않는다.
"""

from __future__ import annotations

import os
import re
import textwrap
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

HOME_ENV = "MADANG_HOME"
DEFAULT_HOME = "~/.madang"
CONFIG_FILE = "config.yaml"
VIEWERS_FILE = "viewers.yaml"
# pinned 뷰어 사본을 해시 이름으로 두는 폴더
CACHE_DIR = "cache"
# core가 고른 포트를 적어 두는 앱 홈 파일
PORT_FILE = "core.port"
ROUTES_KEY = "routes"
RUNNERS_KEY = "runners"
# 프로젝트 설정이 있는 폴더(``<project>/.madang``)
PROJECT_DIR = ".madang"


class ConfigError(ValueError):
    """설정 파일이 올바른 YAML이 아니거나 스키마와 맞지 않는다.

    메시지는 한 줄에 문제 하나씩 ``파일:줄: 키 경로: 설명`` 형식이다.
    """


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class _Strict(BaseModel):
    """모르는 키를 오류로 보는 설정 절. 오타를 위치와 함께 알린다."""

    model_config = ConfigDict(extra="forbid")


# 앱 동작 설정


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

    ledger_tokens: int = 2000
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
    """``config.yaml``에서 ``routes``·``runners`` 절을 뺀 앱 동작 설정."""

    projects: list[ProjectEntry] = Field(default_factory=list)
    core: CoreSettings = Field(default_factory=CoreSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    limits: Limits = Field(default_factory=Limits)
    ui: UiSettings = Field(default_factory=UiSettings)


# 라우팅 표(routes 절)


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
    """``config.yaml`` ``routes`` 절의 라우팅 표."""

    kinds: list[str]
    default_kind: str
    prefix_override: bool = True
    rules: dict[str, list[str]] = Field(default_factory=dict)
    tiers: dict[str, list[Tier]] = Field(default_factory=dict)
    limits: RouteLimits = Field(default_factory=RouteLimits)
    decider: DeciderSettings = Field(default_factory=DeciderSettings)


# 러너(runners 절)


class RunnerSpec(_Model):
    """``config.yaml`` ``runners`` 절의 에이전트 CLI 하나를 시작하는 방법."""

    bin: str
    args: list[str] = Field(default_factory=list)
    auth: str = "subscription"
    cache_ttl: str | None = None


class Config(BaseModel):
    """앱 홈 ``config.yaml``에서 읽은 모든 설정."""

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


@lru_cache(maxsize=1)
def default_data() -> dict[str, Any]:
    """번들된 기본 ``config.yaml``을 읽은 값을 반환한다."""
    return yaml.safe_load(default_text(CONFIG_FILE)) or {}


def load_config(home: str | os.PathLike[str] | None = None) -> Config:
    """앱 홈의 ``config.yaml``을 읽고 검증한다.

    파일이 없으면 번들된 기본값을 쓴다.

    Args:
        home: 앱 홈. ``resolve_home``과 같이 해석한다.

    Returns:
        읽은 설정.

    Raises:
        OSError: 설정 파일을 읽을 수 없는 경우.
        ConfigError: 설정 파일이 올바른 YAML이 아니거나 스키마와 맞지 않는
            경우. 메시지에 파일, 줄, 키 경로가 있다.
    """
    root = resolve_home(home)
    path = root / CONFIG_FILE
    text = (
        path.read_text(encoding="utf-8")
        if path.is_file()
        else default_text(CONFIG_FILE)
    )
    return parse_config(root, path, text)


def parse_config(home: Path, path: Path, text: str) -> Config:
    """``config.yaml`` 텍스트를 검증해 설정으로 만든다.

    최상위 절이 빠져 있으면 그 절만 번들된 기본값으로 채운다.

    Args:
        home: 앱 홈.
        path: 오류 메시지에 보일 파일 경로.
        text: ``config.yaml`` 텍스트.

    Returns:
        읽은 설정.

    Raises:
        ConfigError: 올바른 YAML이 아니거나 스키마와 맞지 않는 경우.
    """
    data = {**default_data(), **_mapping(path, text)}
    routes = data.pop(ROUTES_KEY)
    runners = data.pop(RUNNERS_KEY)
    if not isinstance(runners, dict):
        raise _error(path, text, [((RUNNERS_KEY,), "must be a mapping")])
    return Config(
        home=home,
        madang=_validate(MadangConfig, data, path, text),
        routes=_validate(RoutesConfig, routes, path, text, (ROUTES_KEY,)),
        runners={
            name: _validate(RunnerSpec, spec, path, text, (RUNNERS_KEY, name))
            for name, spec in runners.items()
        },
    )


# 절 단위 편집


def section_text(text: str, key: str) -> str | None:
    """``config.yaml`` 텍스트에서 최상위 절 ``key``의 내용을 반환한다.

    주석을 보존하도록 원문을 잘라 들여쓰기를 걷어 낸다. 절이 한 줄 흐름
    형식이면 값을 YAML로 다시 쓴다.

    Args:
        text: ``config.yaml`` 텍스트.
        key: 최상위 키.

    Returns:
        절의 YAML 텍스트. 절이 없으면 None.
    """
    found = _section(key).search(text)
    if found is None:
        return None
    head, _, rest = found.group(0).partition("\n")
    if _strip_comment(head) != f"{key}:":
        value = (yaml.safe_load(text) or {}).get(key)
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    return textwrap.dedent(rest).rstrip("\n") + "\n"


def replace_section(text: str, key: str, body: str) -> str:
    """최상위 절 ``key``를 ``body``로 바꾼 ``config.yaml`` 텍스트를 반환한다.

    다른 절과 주석, 절 뒤의 빈 줄은 그대로 둔다. 절이 없으면 끝에 붙인다.

    Args:
        text: ``config.yaml`` 텍스트.
        key: 최상위 키.
        body: 절의 새 YAML 텍스트(들여쓰기 없이).

    Returns:
        바뀐 텍스트.
    """
    value = body.strip()
    if "\n" not in value and value[:1] in ("[", "{"):
        block = f"{key}: {value}"
    else:
        block = f"{key}:\n" + textwrap.indent(value, "  ")

    def keep_blank_lines(match: re.Match[str]) -> str:
        old = match.group(0)
        return block + (old[len(old.rstrip("\n")) :] or "\n")

    pattern = _section(key)
    if pattern.search(text):
        return pattern.sub(keep_blank_lines, text, count=1)
    return text.rstrip("\n") + "\n" + block + "\n"


def _section(key: str) -> re.Pattern[str]:
    """최상위 절 ``key``부터 다음 최상위 키나 주석 앞까지를 찾는다.

    목록 항목(``- ``)은 절에 들어간다.
    """
    return re.compile(
        rf"^{re.escape(key)}:.*?(?=^[^\s-]|\Z)", re.MULTILINE | re.DOTALL
    )


def _strip_comment(line: str) -> str:
    return line.split(" #", 1)[0].strip()


# 프로젝트 설정


class RunTarget(_Strict):
    """``runs``의 실행 대상 하나. 선언된 것만 실행 대상이 된다."""

    name: str
    command: str
    cwd: str = "."
    opens: str | None = None


class AutoMerge(_Strict):
    """자동 머지 조건."""

    require_tests: bool = True
    require_no_conflict: bool = True
    test: str | None = None


class ProjectPolicy(_Strict):
    """부작용을 정책이 판단할 때 쓰는 규칙."""

    auto_merge: AutoMerge = Field(default_factory=AutoMerge)
    auto_publish: bool = False
    deny: list[str] = Field(default_factory=list)


class PublishSettings(_Strict):
    """게시 단위: 포함 경로와 대상."""

    include: list[str] = Field(default_factory=list)
    target: str | None = None


class ProjectConfig(_Strict):
    """``<project>/.madang/config.yaml``의 프로젝트 설정.

    Attributes:
        track: 참이면 ``.madang/``을 git에 커밋할 수 있게 둔다. 거짓이면
            ``.git/info/exclude``로 뺀다.
        runs: 실행 대상 목록.
        policy: 자동 머지·자동 게시·금지 명령.
        publish: 게시 설정.
        viewers: 뷰어 이름 -> 이 프로젝트에서 쓸 뷰어 폴더(링크 덮어쓰기).
    """

    track: bool = False
    runs: list[RunTarget] = Field(default_factory=list)
    policy: ProjectPolicy = Field(default_factory=ProjectPolicy)
    publish: PublishSettings = Field(default_factory=PublishSettings)
    viewers: dict[str, str] = Field(default_factory=dict)


def project_config_path(root: Path) -> Path:
    """``<root>/.madang/config.yaml``."""
    return root / PROJECT_DIR / CONFIG_FILE


def load_project_config(root: Path) -> ProjectConfig:
    """프로젝트 설정을 읽고 검증한다. 파일이 없으면 기본값이다.

    Args:
        root: 프로젝트 폴더.

    Returns:
        읽은 설정.

    Raises:
        OSError: 설정 파일을 읽을 수 없는 경우.
        ConfigError: 올바른 YAML이 아니거나 스키마와 맞지 않는 경우.
            메시지에 파일, 줄, 키 경로가 있다.
    """
    path = project_config_path(root)
    if not path.is_file():
        return ProjectConfig()
    text = path.read_text(encoding="utf-8")
    return _validate(ProjectConfig, _mapping(path, text), path, text)


# 검증


def _mapping(path: Path, text: str) -> dict[str, Any]:
    """YAML 텍스트를 매핑으로 읽는다. 빈 파일은 빈 매핑이다."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError(
            f"{_where(path, line)}: invalid YAML: {problem}"
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise _error(path, text, [((), "must be a mapping")])
    return data


def _validate[M: BaseModel](
    model: type[M],
    data: Any,
    path: Path,
    text: str,
    prefix: tuple[str | int, ...] = (),
) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = [
            ((*prefix, *err["loc"]), err["msg"]) for err in exc.errors()
        ]
        raise _error(path, text, problems) from exc


def _error(
    path: Path,
    text: str,
    problems: list[tuple[tuple[str | int, ...], str]],
) -> ConfigError:
    # validate 패키지는 이 모듈을 가져오므로 여기서 늦게 가져온다.
    from madang.validate.issues import Lines

    lines = Lines(text, 1)
    found = []
    for loc, message in problems:
        key = ".".join(str(part) for part in loc) or "(top)"
        found.append(f"{_where(path, lines.key(*loc))}: {key}: {message}")
    return ConfigError("\n".join(found))


def _where(path: Path, line: int | None) -> str:
    return f"{path}:{line}" if line is not None else str(path)
