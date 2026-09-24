"""Page folder model: page.md header, space lookup, and run records."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from madang.store import frontmatter, runs

PAGE_FILE = "page.md"
STATE_FILE = "state.md"
SPACE_FILE = "space.md"

PageStatus = Literal["planning", "doing", "blocked", "review", "done"]
PAGE_STATUSES: tuple[str, ...] = (
    "planning",
    "doing",
    "blocked",
    "review",
    "done",
)


class Page(BaseModel):
    """Header of page.md. Unknown keys are kept."""

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    kind: str | None = None
    status: PageStatus = "planning"
    created: datetime | None = None
    updated: datetime | None = None
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)


def load_page(page_dir: Path) -> tuple[Page, str]:
    """Reads page.md from a page folder.

    Args:
        page_dir: The page folder.

    Returns:
        A ``(header, body)`` tuple.

    Raises:
        OSError: page.md cannot be read.
        FrontmatterError: The front matter cannot be parsed.
        pydantic.ValidationError: The header does not match ``Page``.
    """
    header, body = frontmatter.read(page_dir / PAGE_FILE)
    return Page.model_validate(header), body


def space_dir(page_dir: Path) -> Path | None:
    """Returns the space folder of a page at ``spaces/<slug>/pages/<id>/``.

    Args:
        page_dir: The page folder.

    Returns:
        The space folder, or None when the page is not inside ``pages/``.
    """
    pages = page_dir.resolve().parent
    if pages.name != "pages":
        return None
    return pages.parent


def space_header(page_dir: Path) -> dict[str, Any] | None:
    """Returns the space.md header of a page's space, or None if missing."""
    space = space_dir(page_dir)
    if space is None or not (space / SPACE_FILE).is_file():
        return None
    header, _ = frontmatter.read(space / SPACE_FILE)
    return header


def space_repo(page_dir: Path) -> Path | None:
    """Returns the code repository of the page's space.

    The path comes from ``repo`` in space.md. Relative paths are taken from
    the space folder.

    Args:
        page_dir: The page folder.

    Returns:
        The repository path, or None when the space has no repository or
        cannot be found.
    """
    space = space_dir(page_dir)
    header = space_header(page_dir)
    if space is None or not header or not header.get("repo"):
        return None
    repo = Path(str(header["repo"])).expanduser()
    return repo if repo.is_absolute() else space / repo


def latest_run(page_dir: Path) -> tuple[Path, dict[str, Any]] | None:
    """Returns the highest numbered ``runs/N.json`` and its content.

    Args:
        page_dir: The page folder.

    Returns:
        A ``(path, data)`` tuple, or None when the page has no run.

    Raises:
        ValueError: That file is not a JSON object.
    """
    numbers = runs.list_runs(page_dir)
    if not numbers:
        return None
    path = runs.record_path(page_dir, numbers[-1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a JSON object")
    return path, data


def work_dir(page_dir: Path) -> Path:
    """Returns where an agent works: the space's code repository, if any.

    Args:
        page_dir: The page folder.

    Returns:
        The code repository of the page's space, else the page folder.
    """
    return space_repo(page_dir) or page_dir
