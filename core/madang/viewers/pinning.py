"""pinned 뷰어의 해시와 앱 홈 ``cache/`` 사본.

해시는 뷰어 폴더가 git 작업 트리 안에서 깨끗하면 그 폴더를 마지막으로
바꾼 커밋, 아니면(git 밖, 커밋 전 변경, 추적 안 됨) 폴더 내용의
SHA-256이다. 사본은 ``cache/<해시>/<프로젝트>/<뷰어>/``에 한 번만 만든다.
같은 커밋에 뷰어가 여럿 있어도 이름 폴더로 나뉜다. 뷰어 사본은 이 캐시
밖에 만들지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from madang import config
from madang.store import git
from madang.viewers.manifest import ViewerError

# 접두어로 사본을 찾을 때 요구하는 최소 길이(git 짧은 해시와 같다)
MIN_PREFIX = 7
_SKIPPED = frozenset({".git"})


def content_hash(folder: Path) -> str:
    """폴더 안 파일의 상대 경로와 내용으로 SHA-256을 만든다.

    ``.git`` 폴더는 넣지 않는다.

    Args:
        folder: 뷰어 폴더.

    Returns:
        64자 16진수 해시.
    """
    digest = hashlib.sha256()
    for path in _files(folder):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_pin(folder: Path) -> str:
    """뷰어 폴더의 지금 상태를 가리키는 해시를 반환한다.

    Args:
        folder: 뷰어 폴더.

    Returns:
        깨끗한 git 폴더면 폴더를 마지막으로 바꾼 커밋, 아니면 내용 해시.
    """
    return _clean_commit(folder) or content_hash(folder)


def cache_folder(home: Path, pin: str, name: str) -> Path:
    """고정(pinned) 사본이 놓일 폴더를 반환한다(있는지는 보지 않는다)."""
    return home / config.CACHE_DIR / pin / name


def pin_viewer(home: Path, folder: Path, name: str) -> str:
    """뷰어 폴더를 해시 이름의 캐시에 복사하고 해시를 반환한다.

    같은 해시의 사본이 이미 있으면 그대로 둔다.

    Args:
        home: 앱 홈.
        folder: 뷰어 폴더.
        name: 뷰어 이름(``프로젝트/뷰어``).

    Returns:
        사본의 해시.
    """
    pin = source_pin(folder)
    target = cache_folder(home, pin, name)
    if target.is_dir():
        return pin
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}.")
    )
    try:
        shutil.copytree(
            folder,
            staging,
            ignore=shutil.ignore_patterns(*_SKIPPED),
            dirs_exist_ok=True,
        )
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return pin


def find_pinned(home: Path, pin: str, name: str) -> tuple[str, Path] | None:
    """해시(또는 그 접두어)로 뷰어 사본을 찾는다.

    Args:
        home: 앱 홈.
        pin: 전체 해시, 또는 ``MIN_PREFIX``자 이상의 접두어.
        name: 뷰어 이름.

    Returns:
        ``(전체 해시, 사본 폴더)``. 없으면 None.

    Raises:
        ViewerError: 접두어에 맞는 사본이 둘 이상이다(``pin-ambiguous``).
    """
    exact = cache_folder(home, pin, name)
    if exact.is_dir():
        return pin, exact
    cache = home / config.CACHE_DIR
    if len(pin) < MIN_PREFIX or not cache.is_dir():
        return None
    found = [
        (entry.name, entry / name)
        for entry in sorted(cache.iterdir())
        if entry.name.startswith(pin) and (entry / name).is_dir()
    ]
    if len(found) > 1:
        raise ViewerError(
            "pin-ambiguous", f"{pin!r} matches several copies of {name}"
        )
    return found[0] if found else None


def _files(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and not _SKIPPED.intersection(path.relative_to(folder).parts)
    )


def _clean_commit(folder: Path) -> str | None:
    """깨끗한 추적 폴더를 마지막으로 바꾼 커밋. 아니면 None."""
    try:
        inside = git.run(
            folder, "rev-parse", "--is-inside-work-tree", check=False
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        if git.status(folder):
            return None
        log = git.run(folder, "log", "-1", "--format=%H", "--", ".")
    except git.GitError:
        return None
    return log.stdout.strip() or None
