"""페이지 폴더 모델: page.md 머리부, 프로젝트 찾기, 실행 기록."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from madang.store import frontmatter, runs

PAGE_FILE = "page.md"
STATE_FILE = "state.md"
PROJECT_FILE = "project.md"
MADANG_DIR = ".madang"
PAGES_DIR = "pages"

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


def project_memory(page_dir: Path) -> Path | None:
    """페이지가 속한 프로젝트의 project.md 경로. 프로젝트 밖이면 None."""
    root = project_root(page_dir)
    return None if root is None else root / MADANG_DIR / PROJECT_FILE


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


def work_dir(page_dir: Path) -> Path:
    """에이전트가 일하는 곳을 반환한다. 페이지가 속한 프로젝트 폴더.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        프로젝트 폴더. 프로젝트 밖의 페이지면 페이지 폴더.
    """
    return project_root(page_dir) or page_dir
