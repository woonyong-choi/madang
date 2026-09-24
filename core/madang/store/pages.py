"""페이지 연산: 찾기, 머리부 갱신, 블록 id, 생성, 이동.

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

from madang.store import frontmatter, projects
from madang.store.files import atomic_write
from madang.store.page import LEDGER_FILE, PAGE_FILE

BLOCKS_DIR = "blocks"
LAST_BLOCK_FILE = ".last"
SCRATCH_DIR = "scratch"

_BLOCK_ID = re.compile(r"^b(\d+)$")
_BLOCK_FILE = re.compile(r"^b(\d+)(?:-|\.|$)")
_MESSAGE_HEAD = re.compile(r"^<!--\s*b(\d+)\s*\|", re.MULTILINE)


class PageNotFoundError(LookupError):
    """페이지 id와 맞는 페이지가 없거나 둘 이상이다."""


# 찾기


def find_page(home: Path, page_id: str) -> Path:
    """등록한 프로젝트에서 ``.madang/pages/<page_id>``를 찾는다.

    Args:
        home: 앱 홈 디렉터리.
        page_id: 페이지 id.

    Returns:
        페이지 폴더.

    Raises:
        PageNotFoundError: id가 올바르지 않거나, 그 페이지를 가진 프로젝트가
            없거나 둘 이상이다.
    """
    if (
        not page_id
        or "/" in page_id
        or "\\" in page_id
        or page_id in (".", "..")
    ):
        raise PageNotFoundError(f"invalid page id '{page_id}'")
    matches = [
        (project.id, project.pages_dir / page_id)
        for project in projects.load(Path(home))
        if (project.pages_dir / page_id / PAGE_FILE).is_file()
    ]
    if not matches:
        raise PageNotFoundError(
            f"page '{page_id}' not found in any registered project"
        )
    if len(matches) > 1:
        owners = ", ".join(project for project, _ in matches)
        raise PageNotFoundError(
            f"page '{page_id}' exists in more than one project: {owners}"
        )
    return matches[0][1]


# 머리부


def read_header(path: Path) -> dict[str, Any]:
    """``path``의 머리부 매핑을 반환한다."""
    header, _ = frontmatter.read(path)
    return header


def update_header(
    path: Path,
    mutate: Callable[[dict[str, Any]], None],
    extend_body: str = "",
) -> dict[str, Any]:
    """``mutate``를 거쳐 ``path``의 머리부를 다시 쓴다.

    본문은 그대로 보존하고 파일은 원자적으로 교체한다.

    Args:
        path: 마크다운 파일.
        mutate: 머리부 매핑을 제자리에서 바꾼다.
        extend_body: 본문 끝에 빈 줄 하나를 두고 덧붙일 텍스트.

    Returns:
        새 머리부.

    Raises:
        FrontmatterError: 머리부를 파싱할 수 없다.
    """
    parts = frontmatter.split(path.read_bytes().decode("utf-8"))
    header = frontmatter.load_header(parts)
    mutate(header)
    parts.header = frontmatter.dump_header(header)
    if extend_body:
        old = parts.body.rstrip("\n")
        parts.body = f"{old}\n\n{extend_body}" if old.strip() else extend_body
    atomic_write(path, frontmatter.join(parts))
    return header


def update_state(
    page_dir: Path, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """``update_header``처럼 페이지의 ledger.md 머리부를 다시 쓴다."""
    return update_header(page_dir / LEDGER_FILE, mutate)


def update_page(
    page_dir: Path,
    mutate: Callable[[dict[str, Any]], None],
    extend_body: str = "",
) -> dict[str, Any]:
    """page.md 머리부를 다시 쓰고 ``updated`` 시각을 갱신한다.

    Args:
        page_dir: 페이지 폴더.
        mutate: 머리부 매핑을 제자리에서 바꾼다.
        extend_body: 본문 끝에 덧붙일 텍스트. ``update_header``와 같다.

    Returns:
        새 머리부.
    """

    def wrapped(header: dict[str, Any]) -> None:
        mutate(header)
        header["updated"] = now()

    return update_header(page_dir / PAGE_FILE, wrapped, extend_body)


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
        header, body = frontmatter.read(page_md)
        for item in header.get("blocks") or []:
            if (n := parse_block_id(str(item))) is not None:
                used.add(n)
        used.update(int(n) for n in _MESSAGE_HEAD.findall(body))
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


def append_block(page_dir: Path, block_id: str, text: str = "") -> None:
    """``block_id``가 없으면 page.md ``blocks`` 끝에 추가한다.

    Args:
        page_dir: 페이지 폴더.
        block_id: 블록 id.
        text: 같은 쓰기에서 page.md 본문 끝에 덧붙일 블록 텍스트.
    """

    def mutate(header: dict[str, Any]) -> None:
        blocks = [str(b) for b in header.get("blocks") or []]
        if block_id not in blocks:
            blocks.append(block_id)
        header["blocks"] = blocks

    update_page(page_dir, mutate, text)


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
    pages_dir: Path,
    title: str,
    *,
    slug: str | None = None,
    kind: str = "build",
    goal: str = "",
    day: date | None = None,
) -> Path:
    """page.md와 ledger.md를 가진 페이지 폴더를 만든다.

    폴더는 ``<pages_dir>/<YYYY-MM-DD-slug>/``이다.

    Args:
        pages_dir: 프로젝트의 ``.madang/pages`` 폴더.
        title: 페이지 제목.
        slug: 페이지 슬러그. 기본값은 제목의 슬러그.
        kind: 페이지 종류.
        goal: ledger.md에 적을 목표. 기본값은 제목.
        day: 페이지 id에 들어갈 날짜. 기본값은 오늘.

    Returns:
        페이지 폴더.

    Raises:
        FileNotFoundError: 페이지 폴더를 담을 ``pages_dir``가 없다.
        FileExistsError: 페이지가 이미 있다.
    """
    if not pages_dir.is_dir():
        raise FileNotFoundError(f"{pages_dir} does not exist")
    page_id = f"{(day or date.today()).isoformat()}-{slug or slugify(title)}"
    page_dir = pages_dir / page_id
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
        "reads": [],
    }
    body = STATE_BODY.format(goal=goal or title, next="1. 목표를 구체화한다.")
    (page_dir / LEDGER_FILE).write_text(frontmatter.dumps(state, body), "utf-8")
    return page_dir


def move_page(page_dir: Path, pages_dir: Path) -> Path:
    """페이지 폴더를 다른 프로젝트의 ``.madang/pages``로 옮긴다.

    Args:
        page_dir: 옮길 페이지 폴더.
        pages_dir: 대상 프로젝트의 ``.madang/pages`` 폴더.

    Returns:
        새 페이지 폴더.

    Raises:
        FileNotFoundError: 대상 폴더가 없다.
        FileExistsError: 대상 프로젝트에 같은 id의 페이지가 있다.
    """
    if not pages_dir.is_dir():
        raise FileNotFoundError(f"{pages_dir} does not exist")
    target = pages_dir / page_dir.name
    if target.exists():
        raise FileExistsError(
            f"page '{page_dir.name}' already exists in {pages_dir}"
        )
    shutil.move(str(page_dir), str(target))
    return target


# 도우미


def now() -> datetime:
    """오프셋을 포함한 로컬 시각을 초 단위로 반환한다."""
    return datetime.now().astimezone().replace(microsecond=0)
