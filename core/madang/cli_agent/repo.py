"""코드 저장소 작업: 커밋, 현재 브랜치 푸시, 파일 상태.

푸시는 강제로 하지 않으며, 체크아웃된 브랜치를 같은 이름의 브랜치로만
보낸다.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

from madang import git
from madang.cli_agent.context import AgentError

# 에이전트가 커밋하면 안 되는 파일 이름.
SENSITIVE_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "secrets.yaml",
    "secrets.yml",
    "credentials*.json",
    ".netrc",
    ".npmrc",
    ".pypirc",
)


def require_repo(folder: Path) -> Path:
    """프로젝트 폴더가 git 워크 트리인지 확인하고 반환한다.

    Args:
        folder: 프로젝트 폴더.

    Returns:
        저장소 워크 트리.

    Raises:
        AgentError: 폴더가 없거나 git 워크 트리가 아니다.
    """
    if not folder.is_dir():
        raise AgentError(f"프로젝트 폴더 {folder}가 없다")
    if not git.is_work_tree(folder):
        raise AgentError(f"프로젝트 폴더 {folder}는 git 저장소가 아니다")
    return folder


def sensitive(paths: list[str]) -> list[str]:
    """파일 이름이 ``SENSITIVE_NAMES``와 맞는 경로를 반환한다."""
    return [
        p
        for p in paths
        if any(
            fnmatch.fnmatch(PurePosixPath(p).name, pat)
            for pat in SENSITIVE_NAMES
        )
    ]


def commit_all(repo: Path, message: str) -> str:
    """저장소의 모든 변경을 스테이징하고 커밋한다.

    Args:
        repo: 저장소 워크 트리.
        message: 커밋 메시지.

    Returns:
        새 커밋의 짧은 해시.

    Raises:
        AgentError: 메시지가 비었거나, 변경이 없거나, 변경된 파일이
            민감해 보이거나, git이 실패했다.
    """
    if not message.strip():
        raise AgentError("커밋 메시지가 비어 있다")
    changed = list(git.status(repo))
    if not changed:
        raise AgentError("코드 저장소에 커밋할 변경이 없다")
    blocked = sensitive(changed)
    if blocked:
        raise AgentError(
            "비밀이 들어 있을 수 있는 파일은 커밋하지 않는다: "
            + ", ".join(blocked)
        )
    try:
        git.stage(repo)
        if not git.has_staged_changes(repo):
            raise AgentError("코드 저장소에 커밋할 변경이 없다")
        git.commit(repo, message)
    except git.GitError as exc:
        raise AgentError(str(exc)) from exc
    return git.head(repo)


def push_current(repo: Path) -> tuple[str, str]:
    """현재 브랜치를 강제 없이 리모트로 푸시한다.

    Args:
        repo: 저장소 워크 트리.

    Returns:
        ``(remote, branch)`` 튜플.

    Raises:
        AgentError: HEAD가 분리됐거나, 리모트가 없거나, 푸시가 실패했다.
    """
    branch = git.current_branch(repo)
    if branch is None:
        raise AgentError("HEAD가 분리돼 있다. 브랜치를 체크아웃한 뒤 푸시한다")
    remote = git.upstream_remote(repo, branch)
    remotes = git.remotes(repo)
    if not remote or remote == ".":
        if "origin" not in remotes:
            raise AgentError("코드 저장소에 푸시할 리모트가 없다")
        remote = "origin"
    elif remote not in remotes:
        raise AgentError(f"브랜치 '{branch}'의 리모트 '{remote}'가 없다")
    try:
        git.push(repo, remote, branch)
    except git.GitError as exc:
        raise AgentError(f"{remote}/{branch} 푸시에 실패했다: {exc}") from exc
    return remote, branch
