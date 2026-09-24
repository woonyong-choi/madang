"""git 워크트리: 추가, 제거, 목록, 특정 폴더를 뺀 체크아웃."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from madang.git.command import run
from madang.git.repo import has_branch

_BRANCH_PREFIX = "refs/heads/"


@dataclass(frozen=True)
class Worktree:
    """저장소에 연결된 작업 트리 하나.

    Attributes:
        path: 작업 트리 폴더.
        head: 체크아웃된 커밋 해시. 아직 커밋이 없으면 빈 문자열.
        branch: 체크아웃된 브랜치 이름. 분리됐으면 None.
    """

    path: Path
    head: str
    branch: str | None


def add(repo: Path, path: Path, branch: str, start: str = "HEAD") -> None:
    """``path``에 ``branch``를 체크아웃한 워크트리를 만든다.

    브랜치가 없으면 ``start``에서 새로 만든다.

    Raises:
        GitError: 폴더가 이미 있거나, 브랜치가 다른 곳에 체크아웃돼 있거나,
            ``start``가 없다.
    """
    if has_branch(repo, branch):
        run(repo, "worktree", "add", "-q", str(path), branch)
    else:
        run(repo, "worktree", "add", "-q", "-b", branch, str(path), start)


def remove(repo: Path, path: Path) -> None:
    """워크트리를 지운다. 커밋 안 된 변경이 있으면 지우지 않는다.

    Raises:
        GitError: 변경이 남아 있거나 워크트리가 아니다.
    """
    run(repo, "worktree", "remove", str(path))


def list_worktrees(repo: Path) -> list[Worktree]:
    """메인 체크아웃을 포함한 워크트리 목록을 반환한다."""
    out = run(repo, "worktree", "list", "--porcelain").stdout
    found = []
    for block in out.split("\n\n"):
        fields = dict(
            line.split(" ", 1) if " " in line else (line, "")
            for line in block.splitlines()
        )
        if "worktree" not in fields:
            continue
        branch = fields.get("branch")
        found.append(
            Worktree(
                path=Path(fields["worktree"]),
                head=fields.get("HEAD", ""),
                branch=branch.removeprefix(_BRANCH_PREFIX) if branch else None,
            )
        )
    return found


def leave_out(worktree: Path, folder: str) -> None:
    """워크트리 체크아웃에서 최상위 ``folder``를 뺀다(희소 체크아웃).

    메인 체크아웃에는 영향이 없다. git은 이 설정을 워크트리별 설정에 둔다.

    Raises:
        GitError: git이 실패했다.
    """
    name = folder.strip("/")
    run(worktree, "sparse-checkout", "set", "--no-cone", "/*", f"!/{name}/")
