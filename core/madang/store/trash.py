"""휴지통: 지운 페이지·블록을 ``<project>/.madang/trash/``에 옮겨 둔다.

삭제 하나는 ``trash/<id>/``다. ``entry.json``에 무엇을 지웠는지 적고,
지운 파일은 ``.madang/`` 기준 경로 그대로 ``files/`` 아래에 둔다. 복원은
파일을 원래 자리로 되돌려 옮기고 항목 폴더를 지운다. id는
``<YYYYMMDDTHHMMSSffffff>-<page|bNN>``이다.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from madang.store import blocks, pages
from madang.store.page import MADANG_DIR, PAGE_FILE
from madang.store.projects import Project

DELETE_PAGE = "page"
ENTRY_FILE = "entry.json"
FILES_DIR = "files"
_ID = re.compile(r"^\d{8}T\d{12}-(page|b\d+)$")


class TrashError(ValueError):
    """삭제를 되살릴 수 없다(이미 있는 경로, 사라진 페이지)."""


@dataclass
class TrashEntry:
    """휴지통 항목 하나.

    Attributes:
        id: 항목 id. ``trash/`` 안의 폴더 이름이다.
        deleted: 지운 시각(ISO 8601).
        project: 프로젝트 id.
        page: 페이지 id.
        block: 블록 id. 페이지 전체면 None.
        paths: 지운 프로젝트 기준 경로. 페이지면 페이지 폴더 하나.
        order: 블록을 지우기 전 page.md의 ``blocks`` 순서.
    """

    id: str
    deleted: str
    project: str
    page: str
    block: str | None
    paths: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """API 형태로 반환한다."""
        return {
            "id": self.id,
            "deleted": self.deleted,
            "project": self.project,
            "page": self.page,
            "block": self.block,
            "paths": list(self.paths),
        }


# 지우기


def delete_page(project: Project, page_dir: Path) -> TrashEntry:
    """페이지 폴더를 휴지통으로 옮긴다.

    Args:
        project: 페이지가 속한 프로젝트.
        page_dir: 페이지 폴더.

    Returns:
        새 휴지통 항목.
    """
    entry = _new_entry(project, page_dir.name, None, [page_dir])
    _stash(project, entry, [page_dir])
    return entry


def delete_block(
    project: Project, page_dir: Path, block_id: str, files: list[Path]
) -> TrashEntry:
    """블록 파일을 휴지통으로 옮기고 page.md 순서에서 뺀다.

    Args:
        project: 페이지가 속한 프로젝트.
        page_dir: 페이지 폴더.
        block_id: 블록 id.
        files: 블록의 파일(부속 파일 포함). 메시지 블록이면 빈 목록.

    Returns:
        새 휴지통 항목.
    """
    entry = _new_entry(project, page_dir.name, block_id, files)
    header = pages.read_header(page_dir / PAGE_FILE)
    entry.order = [str(b) for b in header.get("blocks") or []]
    _stash(project, entry, files)
    blocks.remove_from_order(page_dir, block_id)
    return entry


def _new_entry(
    project: Project, page: str, block: str | None, paths: list[Path]
) -> TrashEntry:
    now = datetime.now().astimezone()
    return TrashEntry(
        id=f"{now:%Y%m%dT%H%M%S%f}-{block or DELETE_PAGE}",
        deleted=now.replace(microsecond=0).isoformat(),
        project=project.id,
        page=page,
        block=block,
        paths=[_rel(project, p) for p in paths],
    )


def _stash(project: Project, entry: TrashEntry, paths: list[Path]) -> None:
    folder = project.trash_dir / entry.id
    for path in paths:
        target = folder / FILES_DIR / path.relative_to(project.records)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
    folder.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in entry.__dict__.items() if k != "project"}
    (folder / ENTRY_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )


def _rel(project: Project, path: Path) -> str:
    return path.relative_to(project.root).as_posix()


# 목록과 찾기


def list_trash(projects: list[Project]) -> list[TrashEntry]:
    """프로젝트들의 휴지통 항목을 최신순으로 반환한다.

    Args:
        projects: 훑을 프로젝트.

    Returns:
        휴지통 항목. 읽을 수 없는 항목은 뺀다.
    """
    found = [
        entry for project in projects for entry in _project_entries(project)
    ]
    return sorted(found, key=lambda e: e.id.split("-", 1)[0], reverse=True)


def _project_entries(project: Project) -> list[TrashEntry]:
    if not project.trash_dir.is_dir():
        return []
    entries = []
    for folder in project.trash_dir.iterdir():
        entry = _read(project, folder)
        if entry is not None:
            entries.append(entry)
    return entries


def _read(project: Project, folder: Path) -> TrashEntry | None:
    if not _ID.match(folder.name):
        return None
    try:
        data = json.loads((folder / ENTRY_FILE).read_text(encoding="utf-8"))
        return TrashEntry(
            id=folder.name,
            deleted=str(data["deleted"]),
            project=project.id,
            page=str(data["page"]),
            block=data.get("block"),
            paths=[str(p) for p in data.get("paths") or []],
            order=[str(b) for b in data.get("order") or []],
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def find(projects: list[Project], entry_id: str) -> tuple[Project, TrashEntry]:
    """휴지통 항목을 id로 찾는다.

    Args:
        projects: 훑을 프로젝트.
        entry_id: 항목 id.

    Returns:
        ``(프로젝트, 항목)``.

    Raises:
        LookupError: 휴지통에 그 항목이 없다.
    """
    if _ID.match(entry_id):
        for project in projects:
            entry = _read(project, project.trash_dir / entry_id)
            if entry is not None:
                return project, entry
    raise LookupError(f"'{entry_id}' is not in the trash")


# 복원


def restore(project: Project, entry: TrashEntry) -> Path:
    """휴지통 항목의 파일을 원래 자리로 옮기고 항목을 지운다.

    블록이면 page.md ``blocks``의 원래 자리 근처에 id를 다시 넣는다.

    Args:
        project: 항목이 있는 프로젝트.
        entry: 되살릴 항목.

    Returns:
        페이지 폴더.

    Raises:
        TrashError: 경로가 이미 있거나, 블록의 페이지가 없다.
    """
    page_dir = project.pages_dir / entry.page
    taken = [p for p in entry.paths if (project.root / p).exists()]
    if taken:
        raise TrashError(f"already exists: {', '.join(taken)}")
    if entry.block is not None and not (page_dir / PAGE_FILE).is_file():
        raise TrashError(f"page '{entry.page}' no longer exists")
    folder = project.trash_dir / entry.id
    for rel in entry.paths:
        inside = Path(rel).relative_to(MADANG_DIR)
        target = project.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder / FILES_DIR / inside), str(target))
    if entry.block is not None:
        _reinsert(page_dir, entry.block, entry.order)
    shutil.rmtree(folder, ignore_errors=True)
    return page_dir


def _reinsert(page_dir: Path, block_id: str, before: list[str]) -> None:
    """``before``에서 앞에 있던 블록 중 마지막 것 바로 뒤에 넣는다."""

    def mutate(header: dict[str, Any]) -> None:
        order = [str(b) for b in header.get("blocks") or []]
        if block_id in order:
            return
        if block_id not in before:
            order.append(block_id)
        else:
            earlier = set(before[: before.index(block_id)])
            anchors = [i for i, b in enumerate(order) if b in earlier]
            order.insert(anchors[-1] + 1 if anchors else 0, block_id)
        header["blocks"] = order

    pages.update_page(page_dir, mutate)
