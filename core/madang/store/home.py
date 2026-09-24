"""앱 홈 생성."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from madang import config
from madang.store import git

INIT_MESSAGE = "[home] init"
REMOTE_KEY = "home_remote"
_REMOTE_LINE = re.compile(rf"^{REMOTE_KEY}:.*$", re.MULTILINE)
ROOT_SPACE = "root"
MARKER = f"{config.CONFIG_DIR}/madang.yaml"

# 상대 경로 -> 내장 기본 파일
_FILES: dict[str, str] = {
    **{f"{config.CONFIG_DIR}/{name}": name for name in config.CONFIG_FILES},
    "root.md": "root.md",
    f"spaces/{ROOT_SPACE}/space.md": "space.md",
    ".gitignore": "gitignore",
}

# 자리표시 파일로 git에 유지하는 빈 디렉터리
_DIRS = (f"spaces/{ROOT_SPACE}/pages", "templates")
_KEEP = ".gitkeep"
# core가 실행 중에 두는 파일. 아직 초기화 전인 폴더에 있어도 된다.
RUNTIME_FILES = (config.PORT_FILE, "core.db")


class NotAHomeError(ValueError):
    """다른 내용이 들어 있고 앱 홈이 아닌 폴더."""


@dataclass
class InitResult:
    """``init_home``이 한 일.

    Attributes:
        home: 앱 홈 디렉터리.
        created: 만든 파일의 홈 기준 상대 경로.
        committed: 커밋을 만들었는지 여부.
    """

    home: Path
    created: list[str] = field(default_factory=list)
    committed: bool = False


def init_home(home: Path) -> InitResult:
    """앱 홈 구조를 만들고 커밋한다.

    기존 파일은 절대 덮어쓰지 않는다. 아직 커밋되지 않은 관리 파일은
    init 메시지로 커밋한다.

    Args:
        home: 앱 홈 디렉터리.

    Returns:
        만든 것과 커밋 여부.

    Raises:
        NotAHomeError: 폴더가 비어 있지 않고 ``MARKER``도 없다.
        GitError: git 명령이 실패했다.
        OSError: 파일을 쓸 수 없다.
    """
    home.mkdir(parents=True, exist_ok=True)
    _refuse_foreign(home)
    result = InitResult(home=home)

    for rel, default in _FILES.items():
        path = home / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config.default_text(default), encoding="utf-8")
        result.created.append(rel)

    for rel in _DIRS:
        directory = home / rel
        if directory.exists():
            continue
        directory.mkdir(parents=True)
        (directory / _KEEP).touch()
        result.created.append(f"{rel}/{_KEEP}")

    if not git.is_repo(home):
        git.init(home)

    # 앞서 실패한 init이 커밋하지 못하고 남긴 관리 파일도 함께 처리한다.
    managed = [*_FILES, *(f"{rel}/{_KEEP}" for rel in _DIRS)]
    existing = [rel for rel in managed if (home / rel).exists()]
    committed = git.committed_paths(home, existing)
    pending = [rel for rel in existing if rel not in committed]

    if pending:
        git.add(home, pending)
        if git.has_staged_changes(home):
            git.commit(home, INIT_MESSAGE, pending, unsigned=True)
            result.committed = True

    return result


def is_initialized(home: Path) -> bool:
    """``home``이 초기화된 앱 홈인지(설정 파일이 있는지) 반환한다."""
    return (home / MARKER).is_file()


def remote(home: Path) -> str | None:
    """config/madang.yaml의 ``home_remote``를 반환한다. 없으면 None."""
    path = home / MARKER
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    value = data.get(REMOTE_KEY) if isinstance(data, dict) else None
    return str(value) if value else None


def set_remote(home: Path, address: str) -> None:
    """config/madang.yaml의 ``home_remote`` 줄만 바꾼다. 주석은 그대로다.

    Args:
        home: 초기화된 앱 홈.
        address: git 원격 주소.
    """
    path = home / MARKER
    text = path.read_text(encoding="utf-8")
    line = f"{REMOTE_KEY}: {json.dumps(address)}"
    if _REMOTE_LINE.search(text):
        text = _REMOTE_LINE.sub(lambda _m: line, text, count=1)
    else:
        text = f"{line}\n{text}"
    path.write_text(text, encoding="utf-8")


def _refuse_foreign(home: Path) -> None:
    """``home``이 빈 폴더, 새 저장소, 앱 홈 중 하나가 아니면 예외를 던진다."""
    if (home / MARKER).is_file():
        return
    ignored = (".git", *RUNTIME_FILES)
    others = [p.name for p in home.iterdir() if p.name not in ignored]
    if others or (git.is_repo(home) and git.log_oneline(home)):
        raise NotAHomeError(
            f"{home} is not empty and has no {MARKER}; "
            "refusing to turn it into an app home"
        )
