"""git 모듈: core에서 git을 실행하는 유일한 경로.

앱, 에이전트 CLI, core의 다른 모듈은 git을 직접 실행하지 않고 이 모듈의
함수를 쓴다. 모든 호출은 시간 제한이 있고 터미널 프롬프트를 끈다.
"""

from madang.git.command import GitError, run
from madang.git.repo import (
    Commit,
    MergeResult,
    branches,
    commit,
    create_branch,
    current_branch,
    delete_branch,
    diff,
    exclude,
    has_branch,
    has_staged_changes,
    head,
    is_ancestor,
    is_repository,
    is_work_tree,
    log,
    merge,
    merge_conflicts,
    pull,
    push,
    remotes,
    rev_parse,
    revert,
    stage,
    status,
    upstream_remote,
)
from madang.git.worktree import Worktree

__all__ = [
    "Commit",
    "GitError",
    "MergeResult",
    "Worktree",
    "branches",
    "commit",
    "create_branch",
    "current_branch",
    "delete_branch",
    "diff",
    "exclude",
    "has_branch",
    "has_staged_changes",
    "head",
    "is_ancestor",
    "is_repository",
    "is_work_tree",
    "log",
    "merge",
    "merge_conflicts",
    "pull",
    "push",
    "remotes",
    "rev_parse",
    "revert",
    "run",
    "stage",
    "status",
    "upstream_remote",
]
