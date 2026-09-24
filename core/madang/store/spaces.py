"""공간 만들기·고치기·지우기. 공간의 설정은 space.md 머리부에 둔다."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from madang.store import git, pages, summary
from madang.store.home import ROOT_SPACE
from madang.store.page import SPACE_FILE

# space.md 머리부에 두는 선택 설정.
SETTINGS = ("repo", "parent", "icon", "color", "sort")


class SpaceError(ValueError):
    """공간 요청이 올바르지 않다(없는 상위 공간, 순환 등)."""


def space_path(home: Path, slug: str) -> Path:
    """``spaces/<slug>``를 반환한다.

    Raises:
        FileNotFoundError: 그 공간이 없다.
    """
    if not slug or "/" in slug or slug in (".", ".."):
        raise FileNotFoundError(f"space '{slug}' not found")
    path = home / pages.SPACES_DIR / slug
    if not (path / SPACE_FILE).is_file():
        raise FileNotFoundError(f"space '{slug}' not found")
    return path


def create(
    home: Path, slug: str, title: str, settings: Mapping[str, Any]
) -> Path:
    """공간을 만들고 선택 설정을 space.md에 적는다.

    Args:
        home: 앱 홈.
        slug: 공간 슬러그.
        title: 공간 제목.
        settings: ``SETTINGS`` 중 준 값.

    Returns:
        공간 폴더.

    Raises:
        ValueError: 슬러그가 올바르지 않다.
        SpaceError: 저장소 폴더가 없다.
        FileNotFoundError: 상위 공간이 없다.
        FileExistsError: 공간이 이미 있다.
    """
    _check_repo(settings.get("repo"))
    if settings.get("parent"):
        space_path(home, str(settings["parent"]))
    space = pages.create_space(
        home, slug, title=title, repo=settings.get("repo")
    )
    extra = {k: v for k, v in settings.items() if k != "repo"}
    if extra:
        pages.update_header(space / SPACE_FILE, lambda h: h.update(extra))
    return space


def update(home: Path, slug: str, changes: Mapping[str, Any]) -> None:
    """space.md의 제목과 설정을 바꾼다. None은 설정을 지운다.

    Args:
        home: 앱 홈.
        slug: 공간 슬러그.
        changes: ``title``과 ``SETTINGS`` 중 바꿀 값.

    Raises:
        FileNotFoundError: 공간이나 상위 공간이 없다.
        SpaceError: 상위 공간이 자기 자신이거나 하위 공간이거나, 저장소
            폴더가 없다.
    """
    space = space_path(home, slug)
    if changes.get("repo") is not None:
        _check_repo(changes["repo"])
    parent = changes.get("parent")
    if parent is not None:
        space_path(home, str(parent))
        if str(parent) in _descendants(home, slug) | {slug}:
            raise SpaceError(
                f"space '{parent}' cannot be the parent of '{slug}'"
            )

    def mutate(header: dict[str, Any]) -> None:
        for key, value in changes.items():
            header[key] = value

    pages.update_header(space / SPACE_FILE, mutate)


def _check_repo(repo: Any) -> None:
    if repo is not None and not Path(str(repo)).expanduser().is_dir():
        raise SpaceError(f"code repository {repo} is not a folder")


def _descendants(home: Path, slug: str) -> set[str]:
    parents = {
        space.name: summary.space_summary(space)["parent"]
        for space in summary.space_dirs(home)
    }
    found: set[str] = set()
    frontier = {slug}
    while frontier:
        children = {s for s, p in parents.items() if p in frontier}
        frontier = children - found
        found |= children
    return found


def delete(home: Path, slug: str) -> list[str]:
    """빈 공간을 앱 홈에서 지운다(``git rm``). 커밋은 호출자가 한다.

    Args:
        home: 앱 홈.
        slug: 공간 슬러그.

    Returns:
        지운 앱 홈 기준 경로.

    Raises:
        FileNotFoundError: 공간이 없다.
        SpaceError: 루트 공간이거나 페이지가 남아 있다.
    """
    space = space_path(home, slug)
    if slug == ROOT_SPACE:
        raise SpaceError("the root space cannot be deleted")
    count = len(summary.page_dirs(space))
    if count:
        raise SpaceError(f"space '{slug}' still has {count} pages")
    children = sorted(_descendants(home, slug))
    if children:
        raise SpaceError(
            f"space '{slug}' still has child spaces: {', '.join(children)}"
        )
    rel = space.relative_to(home).as_posix()
    git.run(home, "rm", "-r", "-q", "--ignore-unmatch", "--", rel)
    shutil.rmtree(space, ignore_errors=True)
    return [rel]
