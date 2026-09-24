"""페이지·공간 연산: 찾기, 머리부 갱신, 블록 id, 생성.

머리부 갱신은 YAML 머리부만 다시 쓰며 마크다운 본문은 바이트 단위로
그대로 둔다.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from madang import config
from madang.store import frontmatter, git
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
    """페이지 id와 맞는 페이지가 없거나 둘 이상이다."""


# 찾기


def find_page(home: Path, page_id: str) -> Path:
    """앱 홈 아래의 ``spaces/<slug>/pages/<page_id>``를 반환한다.

    Args:
        home: 앱 홈 디렉터리.
        page_id: 페이지 id.

    Returns:
        페이지 폴더.

    Raises:
        PageNotFoundError: id가 올바르지 않거나, 그 페이지를 가진 공간이
            없거나 둘 이상이다.
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


# 머리부


def read_header(path: Path) -> dict[str, Any]:
    """``path``의 머리부 매핑을 반환한다."""
    header, _ = frontmatter.read(path)
    return header


def update_header(
    path: Path, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """``mutate``를 거쳐 ``path``의 머리부를 다시 쓴다.

    본문은 그대로 보존하고 파일은 원자적으로 교체한다.

    Args:
        path: 마크다운 파일.
        mutate: 머리부 매핑을 제자리에서 바꾼다.

    Returns:
        새 머리부.

    Raises:
        FrontmatterError: 머리부를 파싱할 수 없다.
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
    """``update_header``처럼 페이지의 state.md 머리부를 다시 쓴다."""
    return update_header(page_dir / STATE_FILE, mutate)


def update_page(
    page_dir: Path, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """page.md 머리부를 다시 쓰고 ``updated`` 시각을 갱신한다.

    Args:
        page_dir: 페이지 폴더.
        mutate: 머리부 매핑을 제자리에서 바꾼다.

    Returns:
        새 머리부.
    """

    def wrapped(header: dict[str, Any]) -> None:
        mutate(header)
        header["updated"] = now()

    return update_header(page_dir / PAGE_FILE, wrapped)


# 블록


def format_block_id(n: int) -> str:
    """번호 ``n``의 블록 id를 반환한다. 예: ``b05``."""
    return f"b{n:02d}"


def parse_block_id(block_id: str) -> int | None:
    """``bNN`` 블록 id의 번호를 반환한다. 블록 id가 아니면 None."""
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
    """다음 블록 id를 예약한다.

    id는 늘어나기만 하고 두 번 내주지 않는다. 마지막 번호를
    ``blocks/.last``에 보관해 삭제된 블록의 id를 다시 쓰지 않는다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        새 블록 id.
    """
    n = max(_used_block_numbers(page_dir), default=0) + 1
    blocks = page_dir / BLOCKS_DIR
    blocks.mkdir(parents=True, exist_ok=True)
    atomic_write(blocks / LAST_BLOCK_FILE, f"{n}\n")
    return format_block_id(n)


def append_block(page_dir: Path, block_id: str) -> None:
    """``block_id``가 없으면 page.md ``blocks`` 끝에 추가한다."""

    def mutate(header: dict[str, Any]) -> None:
        blocks = [str(b) for b in header.get("blocks") or []]
        if block_id not in blocks:
            blocks.append(block_id)
        header["blocks"] = blocks

    update_page(page_dir, mutate)


def block_files(page_dir: Path, block_id: str) -> list[Path]:
    """``blocks/``에 있는 블록의 파일을 부속 파일 없이 반환한다.

    Args:
        page_dir: 페이지 폴더.
        block_id: 블록 id.

    Returns:
        ``.meta.yaml`` 부속 파일을 뺀 정렬된 경로.
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


# 생성


def slugify(text: str) -> str:
    """``text``를 소문자와 하이픈으로 구분한 슬러그로 반환한다.

    어떤 문자 체계의 글자든 유지한다. 비면 ``page``를 쓴다.
    """
    norm = unicodedata.normalize("NFKC", text).strip().lower()
    slug = re.sub(r"[^\w]+", "-", norm).strip("-_")
    return slug or "page"


def create_space(
    home: Path, slug: str, *, title: str | None = None, repo: str | None = None
) -> Path:
    """space.md와 빈 pages 폴더를 가진 ``spaces/<slug>/``를 만든다.

    Args:
        home: 앱 홈 디렉터리.
        slug: 공간 슬러그. 이미 올바른 슬러그여야 한다.
        title: 공간 제목. 기본값은 슬러그.
        repo: space.md에 적을 코드 저장소 경로.

    Returns:
        공간 폴더.

    Raises:
        ValueError: 슬러그가 올바르지 않다.
        FileExistsError: 공간이 이미 있다.
    """
    if slugify(slug) != slug:
        raise ValueError(f"invalid space slug '{slug}'")
    space = Path(home) / SPACES_DIR / slug
    if (space / SPACE_FILE).exists():
        raise FileExistsError(f"space '{slug}' already exists")
    (space / PAGES_DIR).mkdir(parents=True, exist_ok=True)
    header = {"slug": slug, "title": title or slug, "repo": repo}
    (space / SPACE_FILE).write_text(
        frontmatter.dumps(header, _default_space_body()), "utf-8"
    )
    return space


def _default_space_body() -> str:
    """앱 홈 기본 space.md와 같은 본문을 반환한다."""
    return frontmatter.split(config.default_text(SPACE_FILE)).body


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
    """page.md, state.md, log.md를 가진 페이지 폴더를 만든다.

    폴더는 ``spaces/<space>/pages/<YYYY-MM-DD-slug>/``이다.

    Args:
        home: 앱 홈 디렉터리.
        space: 공간 슬러그.
        title: 페이지 제목.
        slug: 페이지 슬러그. 기본값은 제목의 슬러그.
        kind: 페이지 종류.
        goal: state.md에 적을 목표. 기본값은 제목.
        day: 페이지 id에 들어갈 날짜. 기본값은 오늘.

    Returns:
        페이지 폴더.

    Raises:
        FileNotFoundError: 공간이 없다.
        FileExistsError: 페이지가 이미 있다.
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


def move_page(home: Path, page_dir: Path, space: str) -> Path:
    """페이지 폴더를 다른 공간으로 옮긴다. 커밋은 호출자가 한다.

    옛 경로는 git 인덱스에서 뺀다. 새 경로는 호출자가 커밋할 때 더한다.

    Args:
        home: 앱 홈.
        page_dir: 옮길 페이지 폴더.
        space: 대상 공간 슬러그.

    Returns:
        새 페이지 폴더.

    Raises:
        FileNotFoundError: 대상 공간이 없다.
        FileExistsError: 대상 공간에 같은 id의 페이지가 있다.
    """
    target_space = Path(home) / SPACES_DIR / space
    if not (target_space / SPACE_FILE).is_file():
        raise FileNotFoundError(f"space '{space}' does not exist")
    target = target_space / PAGES_DIR / page_dir.name
    if target.exists():
        raise FileExistsError(
            f"page '{page_dir.name}' already exists in space '{space}'"
        )
    old = page_dir.relative_to(home).as_posix()
    git.run(home, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", old)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(page_dir), str(target))
    return target


# 도우미


def now() -> datetime:
    """오프셋을 포함한 로컬 시각을 초 단위로 반환한다."""
    return datetime.now().astimezone().replace(microsecond=0)
