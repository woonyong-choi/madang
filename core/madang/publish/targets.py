"""게시 대상: 로컬 폴더와 gh-pages 브랜치에 싣고 되감기.

폴더 대상은 사이트와 똑같이 맞춘다(없는 파일은 지운다). 그래서 비어 있지
않은 폴더는 이전 게시의 사이트(``_madang/site.json``이 있는 폴더)일 때만
쓴다. 게시 전 파일은 게시 기록에 스냅샷으로 남는다.

브랜치 대상은 git 모듈로 사이트 트리를 커밋하고 브랜치만 옮긴다. 작업
트리와 인덱스는 건드리지 않는다. 되감기도 이전 트리를 새 커밋으로 얹어
브랜치가 앞으로만 가게 하므로 원격에 강제로 밀 일이 없다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from madang import git
from madang.policy import Policy
from madang.publish.settings import PublishError
from madang.publish.site import SITE_MANIFEST
from madang.recorder import published
from madang.recorder.published import PublishRecord

# 원격이 이 이름으로 있을 때만 게시 브랜치를 민다.
PUSH_REMOTE = "origin"
PUSH_COMMAND = "push"


# 폴더


def deploy_folder(
    root: Path, site: Path, folder: Path, record: PublishRecord
) -> PublishRecord | None:
    """사이트를 폴더에 싣는다.

    Args:
        root: 프로젝트 폴더(게시 기록이 놓이는 곳).
        site: 만든 사이트 폴더.
        folder: 대상 폴더.
        record: 대상 값이 빈 게시 기록.

    Returns:
        게시 전후 파일 해시를 채운 기록. 폴더가 이미 같으면 None.

    Raises:
        PublishError: 대상이 폴더가 아니거나(``target-invalid``), 게시한
            사이트가 아닌 비어 있지 않은 폴더다(``target-not-site``).
    """
    _check_folder(folder)
    wanted = published.digests(site)
    if published.digests(folder) == wanted:
        return None
    before = published.snapshot(root, folder)
    _mirror(site, folder)
    return record.model_copy(
        update={"before": before, "after": published.digests(folder)}
    )


def rewind_folder(root: Path, folder: Path, record: PublishRecord) -> None:
    """폴더를 게시 전 상태로 되감는다.

    Raises:
        PublishError: 게시 뒤에 폴더가 바뀌었다(``target-changed``).
    """
    if record.before is None or record.after is None:
        raise PublishError(
            "record-invalid", f"publish {record.n} has no folder snapshot"
        )
    if published.digests(folder) != record.after:
        raise PublishError(
            "target-changed", f"{folder} changed after publish {record.n}"
        )
    published.restore(root, folder, record.before)


def _check_folder(folder: Path) -> None:
    if folder.exists() and not folder.is_dir():
        raise PublishError("target-invalid", f"{folder} is not a folder")
    if (
        folder.is_dir()
        and any(folder.iterdir())
        and not (folder / SITE_MANIFEST).is_file()
    ):
        raise PublishError(
            "target-not-site",
            f"{folder} is not empty and holds no published site",
        )


def _mirror(site: Path, folder: Path) -> None:
    """``folder``를 ``site``와 같은 파일 집합으로 맞춘다."""
    wanted = published.digests(site)
    for rel in published.digests(folder).keys() - wanted.keys():
        (folder / rel).unlink()
    for rel in wanted:
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(site / rel, target)
    published.prune_empty(folder)


# 브랜치


def deploy_branch(
    root: Path, site: Path, branch: str, record: PublishRecord
) -> PublishRecord | None:
    """사이트 트리를 브랜치의 새 커밋으로 싣는다.

    Args:
        root: 프로젝트 폴더(저장소 최상위).
        site: 만든 사이트 폴더.
        branch: 게시 브랜치.
        record: 대상 값이 빈 게시 기록.

    Returns:
        게시 전후 커밋을 채운 기록. 브랜치 트리가 이미 같으면 None.

    Raises:
        PublishError: 프로젝트가 git 저장소가 아니다(``not-a-repository``).
        git.GitError: git이 실패했다.
    """
    _check_repository(root)
    before = git.resolve(root, f"refs/heads/{branch}")
    tree = git.write_tree(root, site)
    if before is not None and git.tree_of(root, before) == tree:
        return None
    parents = [before] if before else []
    message = f"Publish site {record.site[:12]}"
    commit = git.commit_tree(root, tree, parents, message)
    git.set_branch(root, branch, commit, before)
    return record.model_copy(
        update={
            "branch": branch,
            "before_commit": before,
            "after_commit": commit,
        }
    )


def rewind_branch(root: Path, record: PublishRecord) -> str:
    """게시 전 트리를 브랜치에 새 커밋으로 얹는다.

    브랜치가 없던 게시는 빈 트리로 되감는다.

    Returns:
        되감은 커밋.

    Raises:
        PublishError: 게시 뒤에 브랜치 내용이 바뀌었다(``target-changed``).
        git.GitError: git이 실패했다.
    """
    branch, after = record.branch, record.after_commit
    if branch is None or after is None:
        raise PublishError(
            "record-invalid", f"publish {record.n} has no branch commit"
        )
    _check_repository(root)
    tip = git.resolve(root, f"refs/heads/{branch}")
    if tip is None or git.tree_of(root, tip) != git.tree_of(root, after):
        raise PublishError(
            "target-changed", f"{branch} changed after publish {record.n}"
        )
    tree = (
        git.tree_of(root, record.before_commit)
        if record.before_commit
        else git.empty_tree(root)
    )
    commit = git.commit_tree(root, tree, [tip], f"Revert publish {record.n}")
    git.set_branch(root, branch, commit, tip)
    return commit


def push_branch(root: Path, branch: str, policy: Policy) -> str | None:
    """원격 ``origin``이 있고 정책이 막지 않으면 브랜치를 민다.

    Args:
        root: 저장소.
        branch: 밀 브랜치.
        policy: 프로젝트 정책. 금지 명령(``check_deny``)이 이 밀기
            (``git push origin <브랜치>``)를 막으면 밀지 않는다.

    Returns:
        민 원격. 밀지 않았으면 None.

    Raises:
        git.GitError: 밀기가 실패했다.
    """
    if PUSH_REMOTE not in git.remotes(root):
        return None
    command = f"git {PUSH_COMMAND} {PUSH_REMOTE} {branch}"
    if not policy.check_deny(command).allowed:
        return None
    git.push(root, PUSH_REMOTE, branch)
    return PUSH_REMOTE


def _check_repository(root: Path) -> None:
    if not git.is_repository(root):
        raise PublishError(
            "not-a-repository", f"{root} is not the top of a git repository"
        )
