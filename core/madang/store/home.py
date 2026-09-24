"""App home creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from madang import config
from madang.store import git

INIT_MESSAGE = "[home] init"
ROOT_SPACE = "root"
MARKER = f"{config.CONFIG_DIR}/madang.yaml"

# relative path -> bundled default file
_FILES: dict[str, str] = {
    **{f"{config.CONFIG_DIR}/{name}": name for name in config.CONFIG_FILES},
    "root.md": "root.md",
    f"spaces/{ROOT_SPACE}/space.md": "space.md",
    ".gitignore": "gitignore",
}

# empty directories kept in git with a placeholder
_DIRS = (f"spaces/{ROOT_SPACE}/pages", "templates")
_KEEP = ".gitkeep"


class NotAHomeError(ValueError):
    """A folder that holds other content and is not an app home."""


@dataclass
class InitResult:
    """What ``init_home`` did.

    Attributes:
        home: The app home directory.
        created: Paths of the files it created, relative to the home.
        committed: Whether it made a commit.
    """

    home: Path
    created: list[str] = field(default_factory=list)
    committed: bool = False


def init_home(home: Path) -> InitResult:
    """Creates the app home layout and commits it.

    Existing files are never overwritten. Managed files that are not yet
    committed are committed with the init message.

    Args:
        home: The app home directory.

    Returns:
        What was created and whether a commit was made.

    Raises:
        NotAHomeError: The folder is not empty and has no ``MARKER``.
        GitError: A git command fails.
        OSError: A file cannot be written.
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

    # Also pick up managed files left uncommitted by an earlier failed init.
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
    """Raises unless ``home`` is empty, a fresh repository, or an app home."""
    if (home / MARKER).is_file():
        return
    others = [p.name for p in home.iterdir() if p.name != ".git"]
    if others or (git.is_repo(home) and git.log_oneline(home)):
        raise NotAHomeError(
            f"{home} is not empty and has no {MARKER}; "
            "refusing to turn it into an app home"
        )
