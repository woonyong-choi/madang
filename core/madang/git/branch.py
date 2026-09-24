"""작업 트리를 거치지 않는 브랜치 쓰기(게시 브랜치)."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

from madang.git.command import identity_args, run


def resolve(repo: Path, ref: str) -> str | None:
    """``ref``가 가리키는 커밋의 전체 해시를 반환한다. 없으면 None."""
    proc = run(
        repo,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{ref}^{{commit}}",
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def tree_of(repo: Path, commit: str) -> str:
    """커밋의 트리 해시를 반환한다."""
    return run(repo, "rev-parse", f"{commit}^{{tree}}").stdout.strip()


def empty_tree(repo: Path) -> str:
    """빈 트리를 저장소에 쓰고 그 해시를 반환한다."""
    return run(
        repo, "hash-object", "-t", "tree", "-w", "--stdin"
    ).stdout.strip()


def write_tree(repo: Path, folder: Path) -> str:
    """``folder``의 파일 전부를 저장소 객체로 쓰고 트리 해시를 반환한다.

    임시 인덱스를 써서 저장소의 인덱스와 작업 트리를 건드리지 않는다.
    무시 규칙과 상관없이 폴더의 모든 파일을 담는다.

    Args:
        repo: 저장소 디렉터리.
        folder: 트리로 만들 폴더. 저장소 밖이어도 된다.

    Returns:
        트리 해시.
    """
    git_dir = run(repo, "rev-parse", "--absolute-git-dir").stdout.strip()
    where = ("--git-dir", git_dir, "--work-tree", str(folder))
    with tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        run(folder, *where, "add", "--all", "--force", ".", env=env)
        return run(folder, *where, "write-tree", env=env).stdout.strip()


def commit_tree(
    repo: Path, tree: str, parents: Sequence[str], message: str
) -> str:
    """트리로 커밋 객체를 만들고 해시를 반환한다(브랜치는 옮기지 않는다).

    저장소에 작성자 정보가 없으면 대체 정보를 쓴다.
    """
    parent_args = [arg for parent in parents for arg in ("-p", parent)]
    return run(
        repo,
        *identity_args(repo),
        "commit-tree",
        tree,
        *parent_args,
        "-m",
        message,
    ).stdout.strip()


def set_branch(repo: Path, branch: str, new: str, old: str | None) -> None:
    """브랜치를 ``new``로 옮긴다. 지금 값이 ``old``일 때만 옮긴다.

    Args:
        repo: 저장소 디렉터리.
        branch: 브랜치 이름.
        new: 새 커밋.
        old: 기대하는 지금 커밋. None이면 브랜치가 없어야 한다.

    Raises:
        GitError: 브랜치가 그 사이 바뀌었다.
    """
    run(repo, "update-ref", f"refs/heads/{branch}", new, old or "")
