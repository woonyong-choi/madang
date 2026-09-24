"""실행이 바꾼 것: 실행 전후에 찍은 폴더 스냅샷.

git 작업 트리면 ``git status``로 변경된 파일만 찍는다. git이 아니거나
기록 폴더(대개 git에서 빠진 ``.madang/``)면 파일 목록 전체를 찍는다.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from madang import git

UNTRACKED = "??"
# 파일 목록으로 찍을 때 들어가지 않는 폴더.
SKIPPED_DIRS = (".git",)


@dataclass(frozen=True)
class Snapshot:
    """한 시점의 폴더에서 변경된(또는 있는) 파일들.

    Attributes:
        codes: 경로별 porcelain 상태 코드. 파일 목록이면 모두 ``??``.
        digests: 경로별 내용 해시.
    """

    codes: dict[str, str] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)

    def changed_since(self, before: Snapshot) -> list[str]:
        """상태나 내용이 ``before``와 다른 경로를 반환한다.

        Args:
            before: 같은 폴더의 이전 스냅샷.

        Returns:
            다시 깨끗해진(또는 지워진) 파일을 포함해 정렬한 경로.
        """
        paths = set(self.codes) | set(before.codes)
        return sorted(
            p
            for p in paths
            if self.codes.get(p) != before.codes.get(p)
            or self.digests.get(p) != before.digests.get(p)
        )

    def new_untracked(self, before: Snapshot) -> list[str]:
        """``before``에는 없던 추적 안 되는 경로를 반환한다."""
        return sorted(
            p
            for p, code in self.codes.items()
            if code == UNTRACKED and p not in before.codes
        )


def take(directory: Path, *, exclude: Sequence[str] = ()) -> Snapshot:
    """``directory`` 아래의 변경된 파일을 기록한다.

    git 작업 트리 밖이면 ``listing``으로 대신한다.

    Args:
        directory: 찍을 폴더.
        exclude: 빼는 폴더(``directory`` 기준 이름).

    Returns:
        스냅샷.
    """
    try:
        codes = git.status(directory)
    except git.GitError:
        return listing(directory, exclude=exclude)
    prefixes = tuple(f"{name.rstrip('/')}/" for name in exclude)
    codes = {p: c for p, c in codes.items() if not p.startswith(prefixes)}
    return Snapshot(
        codes=codes,
        digests={p: _digest(directory / p) for p in codes},
    )


def listing(directory: Path, *, exclude: Sequence[str] = ()) -> Snapshot:
    """``directory`` 아래의 모든 파일을 추적 안 되는 파일로 기록한다.

    Args:
        directory: 찍을 폴더.
        exclude: 빼는 폴더(``directory`` 기준 이름).

    Returns:
        스냅샷. 폴더가 없으면 빈 스냅샷.
    """
    skipped = {name.rstrip("/") for name in (*SKIPPED_DIRS, *exclude)}
    codes: dict[str, str] = {}
    digests: dict[str, str] = {}
    for current, dirs, files in os.walk(directory):
        base = Path(current)
        rel_dir = base.relative_to(directory).as_posix()
        dirs[:] = [
            d
            for d in dirs
            if d not in SKIPPED_DIRS
            and (d if rel_dir == "." else f"{rel_dir}/{d}") not in skipped
        ]
        for name in files:
            path = base / name
            rel = path.relative_to(directory).as_posix()
            codes[rel] = UNTRACKED
            digests[rel] = _digest(path)
    return Snapshot(codes=codes, digests=digests)


def _digest(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return "-"
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()
