"""미등록 파일: 실행이 만들었지만 state.md 산출물로 등록하지 않은 파일.

실행 기록(``runs/N.json``)의 ``unknown_files``를 모으고, 그 뒤 산출물로
등록했거나, 그대로 두기로 했거나(page.md ``kept_files``), 지운 파일은 뺀다.
경로는 페이지 기준이며 코드 저장소 파일은 ``repo:`` 접두가 붙는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from madang.store import git, pages, runs
from madang.store.page import PAGE_FILE, STATE_FILE, space_repo

REPO_PREFIX = "repo:"
KEPT_KEY = "kept_files"
ACTIONS = ("artifact", "keep", "delete")
# 앱 홈이 빈 폴더를 유지하려고 두는 자리표시 파일.
IGNORED_NAMES = (".gitkeep",)


def locate(page_dir: Path, entry: str) -> Path | None:
    """미등록 파일 항목의 실제 경로를 반환한다.

    Args:
        page_dir: 페이지 폴더.
        entry: 페이지 기준 경로 또는 ``repo:<path>``.

    Returns:
        파일 경로. 페이지 폴더나 코드 저장소를 벗어나면 None.
    """
    if entry.startswith(REPO_PREFIX):
        base = space_repo(page_dir)
        rel = entry[len(REPO_PREFIX) :]
    else:
        base, rel = page_dir, entry
    if base is None or not rel or Path(rel).is_absolute():
        return None
    root = base.resolve()
    target = (root / rel).resolve()
    return target if root in target.parents else None


def list_unknown(page_dir: Path) -> list[dict[str, Any]]:
    """아직 처리하지 않은 미등록 파일을 반환한다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        ``{path, run}`` 목록. ``run``은 그 파일을 마지막으로 보고한 실행.
    """
    found: dict[str, int] = {}
    for n in runs.list_runs(page_dir):
        try:
            record = runs.read_run(page_dir, n)
        except (OSError, ValueError):
            continue
        for entry in record.unknown_files:
            found[entry] = n
    settled = _registered(page_dir) | _kept(page_dir)
    return [
        {"path": entry, "run": n}
        for entry, n in found.items()
        if entry not in settled
        and Path(entry).name not in IGNORED_NAMES
        and (path := locate(page_dir, entry)) is not None
        and path.is_file()
    ]


def _registered(page_dir: Path) -> set[str]:
    items = pages.read_header(page_dir / STATE_FILE).get("artifacts")
    return {str(a) for a in items} if isinstance(items, list) else set()


def _kept(page_dir: Path) -> set[str]:
    items = pages.read_header(page_dir / PAGE_FILE).get(KEPT_KEY)
    return {str(a) for a in items} if isinstance(items, list) else set()


def resolve(page_dir: Path, home: Path, entry: str, action: str) -> list[str]:
    """미등록 파일 하나를 등록하거나, 그대로 두거나, 지운다.

    ``artifact``는 state.md ``artifacts``에, ``keep``은 page.md
    ``kept_files``에 더한다. ``delete``는 파일을 지운다. 페이지 파일이면
    ``git rm``한다. 커밋은 호출자가 한다.

    Args:
        page_dir: 페이지 폴더.
        home: 앱 홈.
        entry: 목록에 나온 경로.
        action: ``ACTIONS`` 중 하나.

    Returns:
        바꾼 앱 홈 기준 경로.

    Raises:
        LookupError: ``entry``가 미처리 목록에 없다.
        ValueError: ``action``을 모른다.
    """
    if action not in ACTIONS:
        raise ValueError(f"action '{action}' is not one of {ACTIONS}")
    if entry not in {item["path"] for item in list_unknown(page_dir)}:
        raise LookupError(f"'{entry}' is not an unknown file of this page")
    path = locate(page_dir, entry)
    assert path is not None  # list_unknown이 이미 확인했다
    if action == "artifact":
        pages.update_state(page_dir, lambda h: _append(h, "artifacts", entry))
        return [_rel(page_dir / STATE_FILE, home)]
    if action == "keep":
        pages.update_page(page_dir, lambda h: _append(h, KEPT_KEY, entry))
        return [_rel(page_dir / PAGE_FILE, home)]
    if entry.startswith(REPO_PREFIX):
        path.unlink()
        return []
    rel = _rel(path, home)
    git.run(home, "rm", "-q", "-f", "--ignore-unmatch", "--", rel)
    path.unlink(missing_ok=True)
    return [rel]


def _append(header: dict[str, Any], key: str, entry: str) -> None:
    items = header.get(key)
    items = list(items) if isinstance(items, list) else []
    if entry not in items:
        items.append(entry)
    header[key] = items


def _rel(path: Path, home: Path) -> str:
    return path.resolve().relative_to(home.resolve()).as_posix()
