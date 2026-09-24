"""앱 홈 생성."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from madang import config
from madang.store import git

INIT_MESSAGE = "[home] init"
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


def _refuse_foreign(home: Path) -> None:
    """``home``이 빈 폴더, 새 저장소, 앱 홈 중 하나가 아니면 예외를 던진다."""
    if (home / MARKER).is_file():
        return
    others = [p.name for p in home.iterdir() if p.name != ".git"]
    if others or (git.is_repo(home) and git.log_oneline(home)):
        raise NotAHomeError(
            f"{home} is not empty and has no {MARKER}; "
            "refusing to turn it into an app home"
        )
