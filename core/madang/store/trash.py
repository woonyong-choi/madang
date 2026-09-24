"""휴지통: 앱 홈 git 이력에서 찾은 페이지·블록 삭제와 그 복원.

삭제 커밋 메시지는 ``[<page-id>] delete page`` 또는
``[<page-id>] delete bNN``이다. 목록은 ``git log --diff-filter=D``로 만들고,
복원은 ``git checkout <commit>^ -- <path>`` 뒤 커밋한다. 경로가 다시 있는
삭제(이미 복원한 것)는 목록에서 뺀다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from madang.store import frontmatter, git, pages
from madang.store.page import PAGE_FILE

DELETE_PAGE = "page"
_SUBJECT = re.compile(r"^\[(?P<page>[^\]]+)\] delete (?P<what>\S+)$")
_RECORD = "\x1e"
_FIELD = "\x1f"
_SHA = re.compile(r"^[0-9a-f]{4,40}$")


class TrashError(ValueError):
    """삭제를 되살릴 수 없다(이미 있는 경로, 사라진 페이지)."""


@dataclass
class TrashEntry:
    """삭제 커밋 하나.

    Attributes:
        commit: 삭제 커밋의 짧은 해시.
        deleted: 커밋 시각(ISO 8601).
        space: 공간 슬러그.
        page: 페이지 id.
        block: 블록 id. 페이지 전체면 None.
        paths: 지워진 앱 홈 기준 경로. 페이지면 페이지 폴더 하나.
        message: 커밋 메시지.
    """

    commit: str
    deleted: str
    space: str
    page: str
    block: str | None
    paths: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """API 형태로 반환한다."""
        return {
            "commit": self.commit,
            "deleted": self.deleted,
            "space": self.space,
            "page": self.page,
            "block": self.block,
            "paths": list(self.paths),
            "message": self.message,
        }


def delete_message(page_id: str, what: str) -> str:
    """삭제 커밋 메시지를 반환한다. ``what``은 ``page`` 또는 블록 id."""
    return f"[{page_id}] delete {what}"


def list_trash(home: Path) -> list[TrashEntry]:
    """아직 복원하지 않은 삭제를 최신순으로 반환한다.

    Args:
        home: 앱 홈.

    Returns:
        삭제 목록. 커밋이 없으면 빈 목록.
    """
    if not git.is_repo(home):
        return []
    proc = git.run(
        home,
        "-c",
        "core.quotepath=off",
        "log",
        "--diff-filter=D",
        "--name-only",
        f"--format={_RECORD}%h{_FIELD}%aI{_FIELD}%s",
        "--",
        pages.SPACES_DIR,
        check=False,
    )
    if proc.returncode != 0:
        return []
    entries = []
    for chunk in proc.stdout.split(_RECORD):
        entry = _parse(chunk)
        if entry is not None and not all(
            (home / p).exists() for p in entry.paths
        ):
            entries.append(entry)
    return entries


def _parse(chunk: str) -> TrashEntry | None:
    lines = [line for line in chunk.splitlines() if line.strip()]
    if not lines:
        return None
    sha, stamp, subject = (lines[0].split(_FIELD) + ["", ""])[:3]
    match = _SUBJECT.match(subject)
    if match is None:
        return None
    page, what = match["page"], match["what"]
    block = None if what == DELETE_PAGE else what
    if block is not None and pages.parse_block_id(block) is None:
        return None
    files = [p for p in lines[1:] if f"/{pages.PAGES_DIR}/{page}/" in p]
    if not files:
        return None
    parts = files[0].split("/")
    space = parts[1]
    folder = "/".join(parts[:4])
    return TrashEntry(
        commit=sha,
        deleted=stamp,
        space=space,
        page=page,
        block=block,
        paths=[folder] if block is None else files,
        message=subject,
    )


def find(home: Path, commit: str) -> TrashEntry:
    """휴지통에서 삭제 커밋을 찾는다.

    Args:
        home: 앱 홈.
        commit: 삭제 커밋 해시(짧거나 긴).

    Returns:
        삭제 항목.

    Raises:
        LookupError: 휴지통에 그 커밋이 없다.
    """
    if _SHA.match(commit):
        for entry in list_trash(home):
            if entry.commit.startswith(commit) or commit.startswith(
                entry.commit
            ):
                return entry
    raise LookupError(f"commit '{commit}' is not in the trash")


def restore(home: Path, entry: TrashEntry) -> str:
    """삭제 커밋 직전의 파일을 되살리고 커밋한다.

    블록이면 page.md ``blocks``의 원래 자리 근처에 id를 다시 넣는다.

    Args:
        home: 앱 홈.
        entry: 되살릴 삭제.

    Returns:
        복원 커밋의 짧은 해시.

    Raises:
        TrashError: 경로가 이미 있거나, 블록의 페이지가 없다.
        GitError: git이 실패했다.
    """
    taken = [p for p in entry.paths if (home / p).exists()]
    if taken:
        raise TrashError(f"already exists: {', '.join(taken)}")
    page_dir = home / pages.SPACES_DIR / entry.space / pages.PAGES_DIR
    page_dir = page_dir / entry.page
    if entry.block is not None and not (page_dir / PAGE_FILE).is_file():
        raise TrashError(f"page '{entry.page}' no longer exists")
    git.run(home, "checkout", f"{entry.commit}^", "--", *entry.paths)
    touched = list(entry.paths)
    if entry.block is not None:
        before = _order_before(home, entry, page_dir)
        _reinsert(page_dir, entry.block, before)
        touched.append((page_dir / PAGE_FILE).relative_to(home).as_posix())
    what = entry.block or DELETE_PAGE
    sha = git.commit_changes(home, touched, f"[{entry.page}] restore {what}")
    return sha or git.head(home)


def _order_before(home: Path, entry: TrashEntry, page_dir: Path) -> list[str]:
    rel = (page_dir / PAGE_FILE).relative_to(home).as_posix()
    proc = git.run(home, "show", f"{entry.commit}^:{rel}", check=False)
    if proc.returncode != 0:
        return []
    try:
        header, _ = frontmatter.parse(proc.stdout)
    except frontmatter.FrontmatterError:
        return []
    return [str(b) for b in header.get("blocks") or []]


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
