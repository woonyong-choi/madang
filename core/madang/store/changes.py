"""실행이 바꾼 것: 실행 전후에 찍은 작업 트리 스냅샷."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from madang.store import git

UNTRACKED = "??"


@dataclass(frozen=True)
class Snapshot:
    """한 시점의 폴더에서 변경된 파일들.

    Attributes:
        codes: 변경된 경로별 porcelain 상태 코드.
        digests: 변경된 경로별 내용 해시.
    """

    codes: dict[str, str] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)

    def changed_since(self, before: Snapshot) -> list[str]:
        """상태나 내용이 ``before``와 다른 경로를 반환한다.

        Args:
            before: 같은 폴더의 이전 스냅샷.

        Returns:
            다시 깨끗해진 파일을 포함해 정렬한 경로.
        """
        paths = set(self.codes) | set(before.codes)
        return sorted(
            p
            for p in paths
            if self.codes.get(p) != before.codes.get(p)
            or self.digests.get(p) != before.digests.get(p)
        )

    def new_untracked(self, before: Snapshot) -> list[str]:
        """``before``에서는 변경되지 않았던 추적 안 되는 경로를 반환한다."""
        return sorted(
            p
            for p, code in self.codes.items()
            if code == UNTRACKED and p not in before.codes
        )


def take(directory: Path) -> Snapshot:
    """``directory`` 아래의 변경된 파일을 기록한다.

    Args:
        directory: git 작업 트리 안의 폴더.

    Returns:
        스냅샷. 폴더가 작업 트리 안이 아니면 빈 스냅샷.
    """
    try:
        codes = git.status(directory)
    except git.GitError:
        return Snapshot()
    return Snapshot(
        codes=codes,
        digests={p: _digest(directory / p) for p in codes},
    )


def _digest(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return "-"
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()
