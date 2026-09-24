"""프로젝트: 페이지를 담는 로컬 폴더와 그 등록.

프로젝트의 기록은 ``<project>/.madang/``에 있다(project.md, pages/,
trash/). 어떤 폴더가 프로젝트인지와 표시 설정(제목, 상위 프로젝트, 아이콘,
색, 정렬)은 앱 홈 ``config/madang.yaml``의 ``projects``에 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from madang import config
from madang.store.files import atomic_write
from madang.store.home import MARKER
from madang.store.page import MADANG_DIR, PAGES_DIR, PROJECT_FILE

TRASH_DIR = "trash"
GITIGNORE = ".gitignore"
# madang.yaml 항목에 두는 표시 설정.
SETTINGS = ("parent", "icon", "color", "sort")

_KEY = "projects"
# 다음 최상위 키(또는 주석)까지. 목록 항목(``- ``)은 블록에 들어간다.
_BLOCK = re.compile(rf"^{_KEY}:.*?(?=^[^\s-]|\Z)", re.MULTILINE | re.DOTALL)


class ProjectError(ValueError):
    """프로젝트 요청이 올바르지 않다(폴더 없음, 순환, 하위 프로젝트 등)."""


@dataclass(frozen=True)
class Project:
    """등록한 프로젝트 하나.

    Attributes:
        id: 프로젝트 id. URL과 이벤트에 쓴다.
        root: 프로젝트 폴더.
        title: 제목.
        parent: 상위 프로젝트 id.
        icon: 아이콘.
        color: ``#RRGGBB`` 색.
        sort: 페이지 정렬 기준.
    """

    id: str
    root: Path
    title: str
    parent: str | None = None
    icon: str | None = None
    color: str | None = None
    sort: str | None = None

    @property
    def records(self) -> Path:
        """``<project>/.madang``."""
        return self.root / MADANG_DIR

    @property
    def pages_dir(self) -> Path:
        """``<project>/.madang/pages``."""
        return self.records / PAGES_DIR

    @property
    def trash_dir(self) -> Path:
        """``<project>/.madang/trash``."""
        return self.records / TRASH_DIR

    @property
    def memory(self) -> Path:
        """``<project>/.madang/project.md``(메모리 2층)."""
        return self.records / PROJECT_FILE


# 읽기


def load(home: Path) -> list[Project]:
    """앱 홈에 등록한 프로젝트를 등록 순서대로 반환한다.

    Args:
        home: 앱 홈.

    Returns:
        프로젝트 목록. 설정이 없거나 읽을 수 없으면 빈 목록.
    """
    return [_project(entry) for entry in _entries(home)]


def get(home: Path, project_id: str) -> Project:
    """id로 프로젝트를 찾는다.

    Raises:
        FileNotFoundError: 그 프로젝트가 없다.
    """
    for project in load(home):
        if project.id == project_id:
            return project
    raise FileNotFoundError(f"project '{project_id}' not found")


def owner(home: Path, page_dir: Path) -> Project:
    """페이지 폴더를 가진 프로젝트를 반환한다.

    Raises:
        FileNotFoundError: 그 페이지가 등록한 프로젝트 안에 없다.
    """
    pages_dir = page_dir.resolve().parent
    for project in load(home):
        if project.pages_dir.resolve() == pages_dir:
            return project
    raise FileNotFoundError(f"{page_dir} is not in a registered project")


def _entries(home: Path) -> list[config.ProjectEntry]:
    raw = _raw_settings(home).get(_KEY)
    if not isinstance(raw, list):
        return []
    return [
        config.ProjectEntry.model_validate(item)
        for item in raw
        if isinstance(item, dict) and item.get("id") and item.get("path")
    ]


def _raw_settings(home: Path) -> dict[str, Any]:
    path = home / MARKER
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _project(entry: config.ProjectEntry) -> Project:
    root = Path(entry.path).expanduser()
    return Project(
        id=entry.id,
        root=root,
        title=entry.title or root.name or entry.id,
        parent=entry.parent,
        icon=entry.icon,
        color=entry.color,
        sort=entry.sort,
    )


# 쓰기


def add(
    home: Path,
    path: Path,
    *,
    project_id: str | None = None,
    title: str | None = None,
    settings: Mapping[str, Any] | None = None,
) -> Project:
    """폴더를 프로젝트로 등록하고 ``.madang/``을 만든다.

    이미 있는 ``.madang/`` 파일은 덮어쓰지 않는다.

    Args:
        home: 초기화된 앱 홈.
        path: 프로젝트 폴더. 있어야 한다.
        project_id: 프로젝트 id. 기본값은 폴더 이름의 슬러그.
        title: 제목. 기본값은 폴더 이름.
        settings: ``SETTINGS`` 중 준 값.

    Returns:
        등록한 프로젝트.

    Raises:
        ProjectError: 폴더가 없거나, id가 올바르지 않다.
        FileNotFoundError: 상위 프로젝트가 없다.
        FileExistsError: 같은 폴더나 같은 id의 프로젝트가 이미 있다.
    """
    from madang.store.pages import slugify

    root = path.expanduser().resolve()
    if not root.is_dir():
        raise ProjectError(f"project folder {root} is not a folder")
    known = load(home)
    for project in known:
        if project.root.expanduser().resolve() == root:
            raise FileExistsError(
                f"{root} is already registered as project '{project.id}'"
            )
    taken = {p.id for p in known}
    if project_id is None:
        project_id = _free_id(slugify(root.name), taken)
    elif slugify(project_id) != project_id:
        raise ProjectError(f"invalid project id '{project_id}'")
    elif project_id in taken:
        raise FileExistsError(f"project '{project_id}' already exists")
    extra = {k: v for k, v in (settings or {}).items() if v is not None}
    if extra.get("parent"):
        get(home, str(extra["parent"]))
    create_records(root, commit=_commit_records(home))
    entry: dict[str, Any] = {"id": project_id, "path": str(root)}
    if title:
        entry["title"] = title
    entry.update(extra)
    _save(home, [*_dumped(home), entry])
    return get(home, project_id)


def _free_id(base: str, taken: set[str]) -> str:
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def _commit_records(home: Path) -> bool:
    return bool(_raw_settings(home).get("commit_records"))


def create_records(root: Path, *, commit: bool = False) -> list[str]:
    """``<root>/.madang/``의 기본 구조를 만든다. 있는 파일은 그대로 둔다.

    Args:
        root: 프로젝트 폴더.
        commit: 참이면 기록을 커밋할 수 있는 ``.gitignore``를 쓴다.
            거짓이면 ``.madang/`` 전체를 git에서 뺀다.

    Returns:
        만든 파일과 폴더의 프로젝트 기준 경로.
    """
    records = root / MADANG_DIR
    created: list[str] = []
    for name in (PAGES_DIR, TRASH_DIR):
        folder = records / name
        if not folder.is_dir():
            folder.mkdir(parents=True)
            created.append(f"{MADANG_DIR}/{name}/")
    defaults = {
        GITIGNORE: "gitignore-commit" if commit else "gitignore",
        PROJECT_FILE: PROJECT_FILE,
    }
    for name, default in defaults.items():
        target = records / name
        if not target.exists():
            target.write_text(config.default_text(default), encoding="utf-8")
            created.append(f"{MADANG_DIR}/{name}")
    return created


def update(home: Path, project_id: str, changes: Mapping[str, Any]) -> Project:
    """프로젝트의 제목과 표시 설정을 바꾼다. None은 설정을 지운다.

    Args:
        home: 앱 홈.
        project_id: 프로젝트 id.
        changes: ``title``과 ``SETTINGS`` 중 바꿀 값.

    Returns:
        바뀐 프로젝트.

    Raises:
        FileNotFoundError: 프로젝트나 상위 프로젝트가 없다.
        ProjectError: 상위 프로젝트가 자기 자신이거나 하위 프로젝트다.
    """
    get(home, project_id)
    parent = changes.get("parent")
    if parent is not None:
        get(home, str(parent))
        if str(parent) in descendants(home, project_id) | {project_id}:
            raise ProjectError(
                f"project '{parent}' cannot be the parent of '{project_id}'"
            )
    entries = _dumped(home)
    for entry in entries:
        if entry["id"] != project_id:
            continue
        for key, value in changes.items():
            if value is None:
                entry.pop(key, None)
            else:
                entry[key] = value
    _save(home, entries)
    return get(home, project_id)


def remove(home: Path, project_id: str) -> Project:
    """프로젝트 등록을 지운다. 폴더와 ``.madang/``은 그대로 둔다.

    Args:
        home: 앱 홈.
        project_id: 프로젝트 id.

    Returns:
        등록을 지운 프로젝트.

    Raises:
        FileNotFoundError: 프로젝트가 없다.
        ProjectError: 하위 프로젝트가 남아 있다.
    """
    project = get(home, project_id)
    children = sorted(descendants(home, project_id))
    if children:
        raise ProjectError(
            f"project '{project_id}' still has child projects: "
            + ", ".join(children)
        )
    _save(home, [e for e in _dumped(home) if e["id"] != project_id])
    return project


def descendants(home: Path, project_id: str) -> set[str]:
    """``project_id`` 아래의 모든 하위 프로젝트 id를 반환한다."""
    parents = {p.id: p.parent for p in load(home)}
    found: set[str] = set()
    frontier = {project_id}
    while frontier:
        children = {c for c, p in parents.items() if p in frontier}
        frontier = children - found
        found |= children
    return found


def _dumped(home: Path) -> list[dict[str, Any]]:
    return [entry.model_dump(exclude_none=True) for entry in _entries(home)]


def _save(home: Path, entries: list[dict[str, Any]]) -> None:
    """madang.yaml의 ``projects`` 블록만 바꾼다. 다른 줄과 주석은 그대로다."""
    path = home / MARKER
    text = path.read_text(encoding="utf-8")
    block = yaml.safe_dump(
        {_KEY: entries},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    if _BLOCK.search(text):
        text = _BLOCK.sub(lambda _m: block, text, count=1)
    else:
        text = text.rstrip("\n") + "\n" + block
    atomic_write(path, text)
