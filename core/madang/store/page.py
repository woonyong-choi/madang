"""페이지 폴더 모델: page.md 머리부, 프로젝트 찾기, 실행 기록."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from madang import config
from madang.store import frontmatter, runs

PAGE_FILE = "page.md"
LEDGER_FILE = "ledger.md"
BRIEF_FILE = "brief.md"
MADANG_DIR = config.PROJECT_DIR
PAGES_DIR = "pages"
# 페이지 워크트리를 담는 폴더: 프로젝트 폴더 옆 ``<프로젝트>.wt/``.
WORKTREES_SUFFIX = ".wt"

PageStatus = Literal["planning", "doing", "blocked", "review", "done"]
PAGE_STATUSES: tuple[str, ...] = (
    "planning",
    "doing",
    "blocked",
    "review",
    "done",
)


class Page(BaseModel):
    """page.md의 머리부. 알 수 없는 키는 보존한다."""

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
    """페이지 폴더에서 page.md를 읽는다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        ``(header, body)`` 튜플.

    Raises:
        OSError: page.md를 읽을 수 없다.
        FrontmatterError: 머리부를 파싱할 수 없다.
        pydantic.ValidationError: 머리부가 ``Page``와 맞지 않는다.
    """
    header, body = frontmatter.read(page_dir / PAGE_FILE)
    return Page.model_validate(header), body


def project_root(page_dir: Path) -> Path | None:
    """``<project>/.madang/pages/<id>/``에 있는 페이지의 프로젝트 폴더.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        프로젝트 폴더. 페이지가 ``.madang/pages/`` 안에 없으면 None.
    """
    pages = page_dir.resolve().parent
    if pages.name != PAGES_DIR or pages.parent.name != MADANG_DIR:
        return None
    return pages.parent.parent


def brief_path(page_dir: Path) -> Path | None:
    """페이지가 속한 프로젝트의 brief.md 경로. 프로젝트 밖이면 None."""
    root = project_root(page_dir)
    return None if root is None else root / MADANG_DIR / BRIEF_FILE


def latest_run(page_dir: Path) -> tuple[Path, dict[str, Any]] | None:
    """번호가 가장 큰 ``runs/N.json``과 그 내용을 반환한다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        ``(path, data)`` 튜플. 페이지에 실행이 없으면 None.

    Raises:
        ValueError: 그 파일이 JSON 객체가 아니다.
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


def records_dir(page_dir: Path) -> Path:
    """페이지가 속한 프로젝트의 기록 폴더(``<project>/.madang``).

    코드 페이지는 워크트리에서 돌지만 페이지 파일은 메인 체크아웃의 이
    폴더에 있으므로, 러너가 작업 폴더 밖인 이 폴더에 쓸 수 있어야 한다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        기록 폴더. 프로젝트 밖의 페이지면 페이지 폴더.
    """
    root = project_root(page_dir)
    return page_dir if root is None else root / MADANG_DIR


def worktree_path(root: Path, page_id: str) -> Path:
    """페이지 워크트리 폴더 ``<프로젝트>.wt/<page-id>/``를 반환한다."""
    return root.parent / f"{root.name}{WORKTREES_SUFFIX}" / page_id


def work_dir(page_dir: Path) -> Path:
    """에이전트가 일하는 곳을 반환한다.

    페이지 워크트리가 있으면 그 폴더, 없으면 페이지가 속한 프로젝트 폴더다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        작업 폴더. 프로젝트 밖의 페이지면 페이지 폴더.
    """
    root = project_root(page_dir)
    if root is None:
        return page_dir
    worktree = worktree_path(root, page_dir.name)
    return worktree if worktree.is_dir() else root
