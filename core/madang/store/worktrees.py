"""코딩 페이지의 워크트리: 페이지가 열릴 때 만들고 머지하면 정리한다.

git 프로젝트의 ``kind: code`` 페이지는 ``<프로젝트>.wt/<page-id>/``에 브랜치
``page/<page-id>``로 워크트리를 가진다. 에이전트와 터미널은 그 안에서
일하고, 페이지 폴더는 메인 체크아웃의 ``.madang/``에 남는다. 워크트리
안에는 ``.madang/``을 두지 않는다.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from madang import git
from madang.git import worktree
from madang.store.page import MADANG_DIR, load_page, project_root, worktree_path

CODE_KIND = "code"
BRANCH_PREFIX = "page/"


class PageWorktreeError(RuntimeError):
    """페이지 워크트리를 머지하거나 정리할 수 없다."""


def branch_for(page_id: str) -> str:
    """페이지 워크트리의 브랜치 이름 ``page/<page-id>``."""
    return f"{BRANCH_PREFIX}{page_id}"


def open_page(page_dir: Path) -> Path | None:
    """코딩 페이지가 열릴 때 그 워크트리를 만들고 반환한다.

    이미 있으면 그대로 반환한다. 프로젝트가 git 저장소가 아니거나 페이지
    종류가 ``code``가 아니면 만들지 않는다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        워크트리 폴더. 만들 대상이 아니면 None.

    Raises:
        GitError: 워크트리를 만들 수 없다(커밋이 없는 저장소 등).
    """
    root = project_root(page_dir)
    if root is None or not git.is_repository(root):
        return None
    if load_page(page_dir)[0].kind != CODE_KIND:
        return None
    path = worktree_path(root, page_dir.name)
    if path.is_dir():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    worktree.add(root, path, branch_for(page_dir.name))
    if (path / MADANG_DIR).exists():
        # .madang/을 커밋하는 프로젝트(track: true)도 워크트리에는 두지 않는다.
        worktree.leave_out(path, MADANG_DIR)
    return path


def merge_page(page_dir: Path, message: str | None = None) -> git.MergeResult:
    """페이지 브랜치를 메인 체크아웃의 현재 브랜치에 머지한다.

    머지되면 워크트리와 브랜치를 정리한다. 충돌하면 머지를 취소하고
    워크트리를 그대로 둔다.

    Args:
        page_dir: 페이지 폴더.
        message: 머지 커밋 메시지. 없으면 git 기본 메시지.

    Returns:
        머지 전 해시와 머지 커밋 또는 충돌 파일.

    Raises:
        PageWorktreeError: 페이지 브랜치가 없거나 워크트리에 커밋 안 된
            변경이 있다.
        GitError: 충돌 밖의 이유로 머지가 실패했다.
    """
    root = _root(page_dir)
    branch = branch_for(page_dir.name)
    if not git.has_branch(root, branch):
        raise PageWorktreeError(f"page branch {branch} does not exist")
    path = worktree_path(root, page_dir.name)
    if path.is_dir() and git.status(path):
        raise PageWorktreeError(f"worktree {path} has uncommitted changes")
    result = git.merge(root, branch, message)
    if result.commit is not None:
        close_page(page_dir)
    return result


def close_page(page_dir: Path) -> None:
    """페이지 워크트리와 머지된 브랜치를 지운다.

    커밋 안 된 변경이 있거나 머지되지 않은 브랜치는 지우지 않는다.

    Raises:
        PageWorktreeError: 프로젝트가 git 저장소가 아니다.
        GitError: 변경이 남아 있거나 브랜치가 머지되지 않았다.
    """
    root = _root(page_dir)
    path = worktree_path(root, page_dir.name)
    if path.is_dir():
        worktree.remove(root, path)
        with contextlib.suppress(OSError):
            path.parent.rmdir()  # 마지막 워크트리면 빈 .wt/ 폴더도 지운다
    branch = branch_for(page_dir.name)
    if git.has_branch(root, branch):
        git.delete_branch(root, branch)


def _root(page_dir: Path) -> Path:
    root = project_root(page_dir)
    if root is None or not git.is_repository(root):
        raise PageWorktreeError(f"{page_dir} is not in a git project")
    return root
