"""파일 트리: 작업 폴더의 파일을 렌즈(전체·이 페이지·변경됨)로 거른다.

목록은 사실만 쓴다. git 저장소면 git이 추적하거나 무시하지 않는 파일,
아니면 폴더의 모든 파일이다. ``.madang/``은 늘 맨 앞에 둔다. 실행 배지는
``runs:``에 선언된 ``cwd``에만 붙인다.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from madang import config, git
from madang.recorder.undo import REPO_PREFIX
from madang.store import pages, runs
from madang.store.page import LEDGER_FILE, MADANG_DIR, PAGES_DIR

MAX_ENTRIES = 5000
ARTIFACTS_KEY = "artifacts"
READS_KEY = "reads"


def all_files(folder: Path) -> list[str]:
    """작업 폴더의 파일(폴더 기준 경로). ``.madang/`` 파일이 먼저다."""
    records = _walk(folder / MADANG_DIR, folder)
    if git.is_work_tree(folder):
        out = git.run(
            folder,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ).stdout
        found = [p for p in out.split("\0") if p and (folder / p).is_file()]
    else:
        found = _walk(folder, folder, skip=(MADANG_DIR, ".git"))
    rest = sorted(p for p in set(found) if not _in_records(p))
    return [*records, *rest]


def page_files(page_dir: Path, folder: Path) -> list[str]:
    """페이지가 산출물로 등록하거나, 읽거나, 실행이 바꾼 파일 중 있는 것.

    페이지 폴더 파일은 ``.madang/pages/<id>/`` 아래 경로로 바꾼다.
    """
    header = pages.read_header(page_dir / LEDGER_FILE)
    entries: list[str] = []
    for key in (ARTIFACTS_KEY, READS_KEY):
        items = header.get(key)
        entries += [str(i) for i in items] if isinstance(items, list) else []
    for n in runs.list_runs(page_dir):
        try:
            entries += runs.read_run(page_dir, n).changed_files
        except (OSError, ValueError):
            continue
    page_prefix = f"{MADANG_DIR}/{PAGES_DIR}/{page_dir.name}"
    found = []
    for entry in dict.fromkeys(entries):
        if entry.startswith(REPO_PREFIX):
            path = entry.removeprefix(REPO_PREFIX)
            exists = (folder / path).is_file()
        else:
            path = f"{page_prefix}/{entry}"
            exists = (page_dir / entry).is_file()
        if exists and not PurePosixPath(path).is_absolute():
            found.append(path)
    return found


def changed_files(folder: Path) -> dict[str, str]:
    """git이 알려 준 변경 파일과 두 글자 상태 코드.

    Raises:
        GitError: git 저장소가 아니거나 git이 실패했다.
    """
    return git.status(folder)


def tree(
    files: Iterable[str],
    declared: list[config.RunTarget],
    changes: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """파일 목록을 폴더 항목을 포함한 트리 항목으로 만든다.

    Args:
        files: 폴더 기준 파일 경로. 이 순서를 지킨다.
        declared: 선언된 실행 대상. 그 ``cwd`` 폴더에 배지를 붙인다.
        changes: 경로별 git 상태 코드.

    Returns:
        ``(항목, 최상위 폴더의 실행 배지, 잘렸는지)``.
    """
    badges: dict[str, list[str]] = {}
    for target in declared:
        cwd = PurePosixPath(target.cwd).as_posix().strip("/") or "."
        badges.setdefault(cwd, []).append(target.name)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in files:
        parts = PurePosixPath(path).parts
        for depth in range(1, len(parts)):
            folder = "/".join(parts[:depth])
            if folder not in seen:
                seen.add(folder)
                entries.append(_entry(folder, "dir", badges.get(folder)))
        entry = _entry(path, "file", None)
        if changes and path in changes:
            entry["change"] = changes[path]
        entries.append(entry)
    truncated = len(entries) > MAX_ENTRIES
    return entries[:MAX_ENTRIES], badges.get(".", []), truncated


def _entry(path: str, kind: str, runs_: list[str] | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"path": path, "type": kind}
    if runs_:
        entry["runs"] = runs_
    return entry


def _in_records(path: str) -> bool:
    return PurePosixPath(path).parts[:1] == (MADANG_DIR,)


def _walk(top: Path, base: Path, skip: tuple[str, ...] = ()) -> list[str]:
    found = []
    for current, dirs, names in os.walk(top):
        here = Path(current)
        if here == top:
            dirs[:] = [d for d in dirs if d not in skip]
        dirs.sort()
        for name in sorted(names):
            found.append((here / name).relative_to(base).as_posix())
    return found
