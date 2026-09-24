"""앱이 보여 줄 요약: 공간 목록, 페이지 카드, 페이지 상세.

카드와 상세의 상태는 state.md의 status다. 흐름은 state.md만 갱신하므로
page.md의 status보다 최신이다. state.md를 읽을 수 없으면 page.md의
status를 쓴다.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from madang.store import blocks, frontmatter, pages, runs
from madang.store.log import read_messages
from madang.store.page import (
    PAGE_STATUSES,
    SPACE_FILE,
    STATE_FILE,
    load_page,
)

ACTIVE_STATUSES = ("doing", "blocked")
PREVIEW_CHARS = 120
SORTS = ("updated", "created", "title")
# 페이지 목록에서 무시하는 자리표시 파일.
KEEP_FILE = ".gitkeep"


# 공간


def space_dirs(home: Path) -> list[Path]:
    """space.md가 있는 공간 폴더를 슬러그 순서로 반환한다."""
    root = home / pages.SPACES_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / SPACE_FILE).is_file())


def page_dirs(space: Path) -> list[Path]:
    """공간 안의 페이지 폴더(page.md가 있는 폴더)를 반환한다."""
    folder = space / pages.PAGES_DIR
    if not folder.is_dir():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.name != KEEP_FILE and (p / "page.md").is_file()
    )


def space_summary(space: Path) -> dict[str, Any]:
    """공간 하나의 요약(space.md 머리부와 페이지 수)을 반환한다."""
    header, _ = frontmatter.read(space / SPACE_FILE)
    found = page_dirs(space)
    active = sum(page_status(p) in ACTIVE_STATUSES for p in found)
    summary: dict[str, Any] = {
        "slug": space.name,
        "title": str(header.get("title") or space.name),
        "repo": _optional(header.get("repo")),
        "parent": _optional(header.get("parent")),
        "icon": _optional(header.get("icon")),
        "color": _optional(header.get("color")),
        "sort": _sort(header),
        "pages": len(found),
        "active_pages": active,
    }
    return summary


def _optional(value: Any) -> str | None:
    return None if value is None else str(value)


def _sort(header: dict[str, Any]) -> str:
    value = header.get("sort")
    return value if value in SORTS else "updated"


# 페이지 카드


def page_status(page_dir: Path) -> str:
    """페이지의 현재 상태(state.md, 없으면 page.md)를 반환한다."""
    for name in (STATE_FILE, "page.md"):
        try:
            status = pages.read_header(page_dir / name).get("status")
        except (OSError, frontmatter.FrontmatterError):
            continue
        if status in PAGE_STATUSES:
            return str(status)
    return "planning"


def page_card(page_dir: Path) -> dict[str, Any]:
    """페이지 목록의 카드 하나를 반환한다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        제목, 상태, 마지막 메시지 한 줄, 블록 종류별 개수, 마지막 실행,
        갱신 시각, 고정, 태그, 첫 view 블록.
    """
    page, _ = load_page(page_dir)
    headers = blocks.page_blocks(page_dir, page.blocks)
    numbers = runs.list_runs(page_dir)
    counts = Counter(h["type"] for h in headers)
    if numbers:
        counts["run"] = len(numbers)
    card: dict[str, Any] = {
        "id": page.id,
        "space": page_dir.parent.parent.name,
        "title": page.title,
        "kind": page.kind,
        "status": page_status(page_dir),
        "created": page.created,
        "updated": page.updated,
        "pinned": page.pinned,
        "tags": list(page.tags),
        "preview": preview(page_dir),
        "block_counts": dict(counts),
        "first_view": next(
            (h["id"] for h in headers if h["type"] == "view"), None
        ),
    }
    if numbers and (ref := _run_ref(page_dir, numbers[-1])) is not None:
        card["last_run"] = ref
    return card


def preview(page_dir: Path) -> str | None:
    """마지막 메시지의 첫 줄을 반환한다. 메시지가 없으면 None."""
    messages = read_messages(page_dir)
    if not messages:
        return None
    line = next(
        (ln.strip() for ln in messages[-1].text.splitlines() if ln.strip()),
        "",
    )
    if len(line) > PREVIEW_CHARS:
        line = line[: PREVIEW_CHARS - 1] + "…"
    return line or None


def _run_ref(page_dir: Path, n: int) -> dict[str, Any] | None:
    try:
        record = runs.read_run(page_dir, n)
    except (OSError, ValueError):
        return None
    if not record.runner or not record.model:
        return None
    ref: dict[str, Any] = {
        "n": record.n,
        "runner": record.runner,
        "model": record.model,
    }
    if record.result_status:
        ref["result_status"] = record.result_status
    return ref


def sort_cards(cards: list[dict[str, Any]], order: str) -> list[dict[str, Any]]:
    """고정 카드를 먼저, 그다음 공간의 정렬 기준으로 카드를 정렬한다.

    Args:
        cards: 페이지 카드.
        order: ``updated``(최신순), ``created``(최신순), ``title``(가나다순).

    Returns:
        정렬한 새 목록.
    """
    if order == "title":
        ordered = sorted(cards, key=lambda c: str(c["title"]))
    else:
        ordered = sorted(
            cards, key=lambda c: _stamp(c.get(order)), reverse=True
        )
    return sorted(ordered, key=lambda c: not c["pinned"])


def _stamp(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else 0.0


# 페이지 상세


def page_detail(page_dir: Path) -> dict[str, Any]:
    """page.md, 본문 순서의 블록 머리부, 실행 기록을 반환한다.

    ``unknown_files``와 ``waiting``은 호출자가 채운다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        페이지 상세.
    """
    page, body = load_page(page_dir)
    records = _records(page_dir)
    triggered = {
        str((r.trigger or {}).get("message")): r.n
        for r in reversed(records)
        if r.trigger
    }
    headers = blocks.page_blocks(page_dir, page.blocks)
    for header in headers:
        unset = header["type"] == "message" and "run" not in header
        if unset and header["id"] in triggered:
            header["run"] = triggered[header["id"]]
    return {
        "id": page.id,
        "space": page_dir.parent.parent.name,
        "title": page.title,
        "kind": page.kind,
        "status": page_status(page_dir),
        "created": page.created,
        "updated": page.updated,
        "pinned": page.pinned,
        "tags": list(page.tags),
        "overview": body,
        "blocks": headers,
        "runs": [run_record(r) for r in records],
    }


def _records(page_dir: Path) -> list[runs.RunRecord]:
    found = []
    for n in runs.list_runs(page_dir):
        try:
            found.append(runs.read_run(page_dir, n))
        except (OSError, ValueError):
            continue
    return found


INPUT_PARTS = (
    "system_est",
    "root",
    "space",
    "state",
    "contract",
    "target",
    "request",
)


def run_input(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """실행 입력 추정을 모든 부분이 있는 형태로 반환한다.

    대상 블록이 없던 실행은 ``target``이 없으므로 0으로 채운다.
    """
    if not data:
        return None
    parts = dict(data.get("parts") or {})
    for name in INPUT_PARTS:
        parts.setdefault(name, 0)
    return {**data, "parts": parts, "total_est": data.get("total_est", 0)}


def run_record(record: runs.RunRecord) -> dict[str, Any]:
    """실행 기록을 API 형태(JSON 값)로 반환한다."""
    data = record.model_dump(mode="json")
    data["input"] = run_input(data.get("input"))
    return {k: v for k, v in data.items() if v is not None}
