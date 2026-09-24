"""App home creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from madang import config
from madang.store import git

INIT_MESSAGE = "[home] init"
ROOT_SPACE = "root"

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


@dataclass
class InitResult:
    home: Path
    created: list[str] = field(default_factory=list)
    committed: bool = False


def init_home(home: Path) -> InitResult:
    """Create the app home layout. Existing files are never overwritten."""
    home.mkdir(parents=True, exist_ok=True)
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
            git.commit(home, INIT_MESSAGE, pending)
            result.committed = True

    return result
