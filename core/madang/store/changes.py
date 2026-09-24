"""What a run changed: work tree snapshots taken before and after it."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from madang.store import git

UNTRACKED = "??"


@dataclass(frozen=True)
class Snapshot:
    """The dirty files of a folder at one moment.

    Attributes:
        codes: Each dirty path mapped to its porcelain status code.
        digests: Each dirty path mapped to a digest of its content.
    """

    codes: dict[str, str] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)

    def changed_since(self, before: Snapshot) -> list[str]:
        """Returns the paths whose status or content differs from ``before``.

        Args:
            before: The earlier snapshot of the same folder.

        Returns:
            Sorted paths, including files that became clean again.
        """
        paths = set(self.codes) | set(before.codes)
        return sorted(
            p
            for p in paths
            if self.codes.get(p) != before.codes.get(p)
            or self.digests.get(p) != before.digests.get(p)
        )

    def new_untracked(self, before: Snapshot) -> list[str]:
        """Returns untracked paths that were not dirty in ``before``."""
        return sorted(
            p
            for p, code in self.codes.items()
            if code == UNTRACKED and p not in before.codes
        )


def take(directory: Path) -> Snapshot:
    """Records the dirty files under ``directory``.

    Args:
        directory: A folder inside a git work tree.

    Returns:
        The snapshot. Empty when the folder is not in a work tree.
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
