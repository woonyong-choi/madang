"""Page and space operations: lookup, header updates, block ids, creation.

Header updates rewrite only the YAML front matter; the Markdown body is kept
byte for byte.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from madang.store import frontmatter
from madang.store.files import atomic_write
from madang.store.page import PAGE_FILE, SPACE_FILE, STATE_FILE

SPACES_DIR = "spaces"
PAGES_DIR = "pages"
BLOCKS_DIR = "blocks"
LOG_FILE = "log.md"
LAST_BLOCK_FILE = ".last"

_BLOCK_ID = re.compile(r"^b(\d+)$")
_BLOCK_FILE = re.compile(r"^b(\d+)(?:-|\.|$)")
_LOG_BLOCK = re.compile(r"^<!--\s*b(\d+)\s*\|", re.MULTILINE)


class PageNotFoundError(LookupError):
    """No page, or more than one, matches a page id."""


# lookup


def find_page(home: Path, page_id: str) -> Path:
    """Returns ``spaces/<slug>/pages/<page_id>`` under the app home.

    Args:
        home: The app home directory.
        page_id: The page id.

    Returns:
        The page folder.

    Raises:
        PageNotFoundError: The id is invalid, or no space (or more than one) has
            the page.
    """
    if (
        not page_id
        or "/" in page_id
        or "\\" in page_id
        or page_id in (".", "..")
    ):
        raise PageNotFoundError(f"invalid page id '{page_id}'")
    matches = sorted(
        p
        for p in (Path(home) / SPACES_DIR).glob(f"*/{PAGES_DIR}/{page_id}")
        if (p / PAGE_FILE).is_file()
    )
    if not matches:
        raise PageNotFoundError(
            f"page '{page_id}' not found under {Path(home) / SPACES_DIR}"
        )
    if len(matches) > 1:
        spaces = ", ".join(p.parent.parent.name for p in matches)
        raise PageNotFoundError(
            f"page '{page_id}' exists in more than one space: {spaces}"
        )
    return matches[0]


# headers


def read_header(path: Path) -> dict[str, Any]:
    """Returns the front matter mapping of ``path``."""
    header, _ = frontmatter.read(path)
    return header


def update_header(
    path: Path, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """Rewrites the front matter of ``path`` through ``mutate``.

    The body is preserved exactly and the file is replaced atomically.

    Args:
        path: The Markdown file.
        mutate: Changes the header mapping in place.

    Returns:
        The new header.

    Raises:
        FrontmatterError: The front matter cannot be parsed.
    """
    parts = frontmatter.split(path.read_bytes().decode("utf-8"))
    header = frontmatter.load_header(parts)
    mutate(header)
    parts.header = frontmatter.dump_header(header)
    atomic_write(path, frontmatter.join(parts))
    return header


def update_state(
    page_dir: Path, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """Rewrites the state.md header of a page as in ``update_header``."""
    return update_header(page_dir / STATE_FILE, mutate)


def update_page(
    page_dir: Path, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """Rewrites the page.md header and refreshes its ``updated`` time.

    Args:
        page_dir: The page folder.
        mutate: Changes the header mapping in place.

    Returns:
        The new header.
    """

    def wrapped(header: dict[str, Any]) -> None:
        mutate(header)
        header["updated"] = now()

    return update_header(page_dir / PAGE_FILE, wrapped)


# blocks


def format_block_id(n: int) -> str:
    """Returns the block id for number ``n``, e.g. ``b05``."""
    return f"b{n:02d}"


def parse_block_id(block_id: str) -> int | None:
    """Returns the number of a ``bNN`` block id, or None if it is not one."""
    m = _BLOCK_ID.match(block_id)
    return int(m.group(1)) if m else None


def _used_block_numbers(page_dir: Path) -> set[int]:
    used: set[int] = set()
    page_md = page_dir / PAGE_FILE
    if page_md.is_file():
        for item in read_header(page_md).get("blocks") or []:
            if (n := parse_block_id(str(item))) is not None:
                used.add(n)
    blocks = page_dir / BLOCKS_DIR
    if blocks.is_dir():
        for p in blocks.iterdir():
            if m := _BLOCK_FILE.match(p.name):
                used.add(int(m.group(1)))
        last = blocks / LAST_BLOCK_FILE
        if (
            last.is_file()
            and (text := last.read_text(encoding="utf-8").strip()).isdigit()
        ):
            used.add(int(text))
    log = page_dir / LOG_FILE
    if log.is_file():
        used.update(
            int(n) for n in _LOG_BLOCK.findall(log.read_text(encoding="utf-8"))
        )
    return used


def allocate_block(page_dir: Path) -> str:
    """Reserves the next block id.

    Ids grow and are never handed out twice. The last number is kept in
    ``blocks/.last`` so ids of deleted blocks are not reused.

    Args:
        page_dir: The page folder.

    Returns:
        The new block id.
    """
    n = max(_used_block_numbers(page_dir), default=0) + 1
    blocks = page_dir / BLOCKS_DIR
    blocks.mkdir(parents=True, exist_ok=True)
    atomic_write(blocks / LAST_BLOCK_FILE, f"{n}\n")
    return format_block_id(n)


def append_block(page_dir: Path, block_id: str) -> None:
    """Adds ``block_id`` to the end of page.md ``blocks`` if it is missing."""

    def mutate(header: dict[str, Any]) -> None:
        blocks = [str(b) for b in header.get("blocks") or []]
        if block_id not in blocks:
            blocks.append(block_id)
        header["blocks"] = blocks

    update_page(page_dir, mutate)


def block_files(page_dir: Path, block_id: str) -> list[Path]:
    """Returns the files of a block in ``blocks/``, without sidecars.

    Args:
        page_dir: The page folder.
        block_id: The block id.

    Returns:
        Sorted paths, excluding ``.meta.yaml`` sidecars.
    """
    blocks = page_dir / BLOCKS_DIR
    if not blocks.is_dir() or parse_block_id(block_id) is None:
        return []
    return sorted(
        p
        for p in blocks.iterdir()
        if p.is_file()
        and (
            p.name.startswith(f"{block_id}-")
            or p.name.startswith(f"{block_id}.")
        )
        and not p.name.endswith(".meta.yaml")
    )


# creation


def slugify(text: str) -> str:
    """Returns a lowercase, hyphen separated slug of ``text``.

    Letters of any script are kept. Falls back to ``page``.
    """
    norm = unicodedata.normalize("NFKC", text).strip().lower()
    slug = re.sub(r"[^\w]+", "-", norm).strip("-_")
    return slug or "page"


def create_space(
    home: Path, slug: str, *, title: str | None = None, repo: str | None = None
) -> Path:
    """Creates ``spaces/<slug>/`` with space.md and an empty pages folder.

    Args:
        home: The app home directory.
        slug: The space slug. Must already be a valid slug.
        title: The space title. Defaults to the slug.
        repo: The code repository path for space.md.

    Returns:
        The space folder.

    Raises:
        ValueError: The slug is invalid.
        FileExistsError: The space already exists.
    """
    if slugify(slug) != slug:
        raise ValueError(f"invalid space slug '{slug}'")
    space = Path(home) / SPACES_DIR / slug
    if (space / SPACE_FILE).exists():
        raise FileExistsError(f"space '{slug}' already exists")
    (space / PAGES_DIR).mkdir(parents=True, exist_ok=True)
    header = {"slug": slug, "title": title or slug, "repo": repo}
    (space / SPACE_FILE).write_text(
        frontmatter.dumps(
            header, "Notes shared by every page in this space.\n"
        ),
        "utf-8",
    )
    return space


STATE_BODY = """## 목표
{goal}

## 결정 사항

## 현재 상태

## 다음 할 일
{next}

## 막힌 점

## 로그
"""


def create_page(
    home: Path,
    space: str,
    title: str,
    *,
    slug: str | None = None,
    kind: str = "build",
    goal: str = "",
    day: date | None = None,
) -> Path:
    """Creates a page folder with page.md, state.md, and log.md.

    The folder is ``spaces/<space>/pages/<YYYY-MM-DD-slug>/``.

    Args:
        home: The app home directory.
        space: The space slug.
        title: The page title.
        slug: The page slug. Defaults to a slug of the title.
        kind: The page kind.
        goal: The goal written to state.md. Defaults to the title.
        day: The date in the page id. Defaults to today.

    Returns:
        The page folder.

    Raises:
        FileNotFoundError: The space does not exist.
        FileExistsError: The page already exists.
    """
    space_dir = Path(home) / SPACES_DIR / space
    if not (space_dir / SPACE_FILE).is_file():
        raise FileNotFoundError(f"space '{space}' does not exist")
    page_id = f"{(day or date.today()).isoformat()}-{slug or slugify(title)}"
    page_dir = space_dir / PAGES_DIR / page_id
    if page_dir.exists():
        raise FileExistsError(f"page '{page_id}' already exists")
    (page_dir / BLOCKS_DIR).mkdir(parents=True)
    stamp = now()
    page = {
        "id": page_id,
        "title": title,
        "kind": kind,
        "status": "planning",
        "created": stamp,
        "updated": stamp,
        "pinned": False,
        "tags": [],
        "blocks": [],
    }
    (page_dir / PAGE_FILE).write_text(frontmatter.dumps(page, ""), "utf-8")
    state = {
        "status": "planning",
        "kind": kind,
        "tier": 1,
        "attempts": 0,
        "decisions": [],
        "tasks": [],
        "artifacts": [],
    }
    body = STATE_BODY.format(goal=goal or title, next="1. 목표를 구체화한다.")
    (page_dir / STATE_FILE).write_text(frontmatter.dumps(state, body), "utf-8")
    (page_dir / LOG_FILE).write_text("", "utf-8")
    return page_dir


# helpers


def now() -> datetime:
    """Returns the local time with its offset, to the second."""
    return datetime.now().astimezone().replace(microsecond=0)
