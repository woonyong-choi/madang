"""git 경로: 앱 git 탭의 상태·디프·스테이지·커밋·브랜치·워크트리·이력·원격.

git은 core ``git`` 모듈만 실행한다. 모든 쓰기는 먼저 프로젝트 정책의
금지 명령(``policy.deny``)을 확인하고, 끝나면 ``git.changed``로 알린다.
``page``를 주면 그 페이지의 워크트리(있으면)에서 일한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Query

from madang import git
from madang.api import errors, models, workspace
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.cli_agent import repo as coderepo
from madang.cli_agent.context import AgentError
from madang.git import worktree
from madang.store import projects
from madang.store.page import worktree_path

# 계약의 태그. 목록 첫 자리에 두면 git 실행 검사에 걸리므로 이름으로 둔다.
TAG = "git"
router = Router(tags=[TAG])

PageQuery = Annotated[
    str | None,
    Query(description="이 페이지의 워크트리에서 일한다(있을 때)."),
]
LOG_LIMIT = 50


def _folder(
    core: Core, project: str, page: str | None
) -> tuple[projects.Project, Path]:
    found = core.project(project)
    page_dir = workspace.page_in(core, found, page)
    return found, workspace.work_folder(found, page_dir)


def _repo(
    core: Core, project: str, page: str | None
) -> tuple[projects.Project, Path]:
    found, folder = _folder(core, project, page)
    return found, workspace.require_repo(folder)


def _git_failed(exc: git.GitError) -> errors.HttpError:
    return errors.conflict(str(exc))


def git_status(folder: Path) -> models.GitStatus:
    """작업 트리의 상태. git 저장소가 아니면 ``repository``가 거짓이다."""
    if not git.is_work_tree(folder):
        return models.GitStatus(repository=False, folder=str(folder), files=[])
    try:
        head = git.rev_parse(folder)
    except git.GitError:
        head = None  # 아직 커밋이 없다
    files = [
        models.GitFile(path=path, code=code)
        for path, code in sorted(git.status(folder).items())
    ]
    return models.GitStatus(
        repository=True,
        folder=str(folder),
        branch=git.current_branch(folder),
        head=head,
        files=files,
    )


@router.get("/projects/{project}/git/status", operation_id="getGitStatus")
def get_status(
    project: str, core: CoreDep, page: PageQuery = None
) -> models.GitStatus:
    """변경된 파일, 브랜치, HEAD."""
    _, folder = _folder(core, project, page)
    try:
        return git_status(folder)
    except git.GitError as exc:
        raise _git_failed(exc) from exc


@router.get("/projects/{project}/git/diff", operation_id="getGitDiff")
def get_diff(
    project: str,
    core: CoreDep,
    page: PageQuery = None,
    staged: bool = False,
    base: str | None = None,
    target: str | None = None,
    path: Annotated[list[str] | None, Query()] = None,
) -> models.GitDiff:
    """통합 diff 텍스트."""
    _, repo = _repo(core, project, page)
    try:
        text = git.diff(repo, base, target, staged=staged, paths=path or ())
    except git.GitError as exc:
        raise _git_failed(exc) from exc
    return models.GitDiff(text=text)


@router.post("/projects/{project}/git/stage", operation_id="stageGit")
def stage(
    project: str,
    body: models.GitStage,
    core: CoreDep,
    page: PageQuery = None,
) -> models.GitStatus:
    """변경을 스테이징한다. ``paths``가 없으면 모든 변경이다."""
    found, repo = _repo(core, project, page)
    workspace.allow(found, "git add -A")
    try:
        git.stage(repo, body.paths)
        status = git_status(repo)
    except git.GitError as exc:
        raise _git_failed(exc) from exc
    core.announce_git(found.id, repo, "stage")
    return status


@router.post("/projects/{project}/git/commit", operation_id="commitGit")
def commit(
    project: str,
    body: models.GitCommitCreate,
    core: CoreDep,
    page: PageQuery = None,
) -> models.RepoCommitResult:
    """스테이징된 변경을 커밋한다. ``paths``를 주면 그 경로만 커밋한다."""
    found, repo = _repo(core, project, page)
    if not body.message.strip():
        raise errors.invalid("commit message is empty")
    workspace.allow(found, "git commit")
    blocked = coderepo.sensitive(list(git.status(repo)))
    if blocked:
        raise errors.conflict(
            "files that may hold secrets are not committed: "
            + ", ".join(blocked)
        )
    if not body.paths and not git.has_staged_changes(repo):
        raise errors.conflict("nothing is staged")
    try:
        sha = git.commit(repo, body.message, body.paths)
    except git.GitError as exc:
        raise _git_failed(exc) from exc
    core.announce_git(found.id, repo, "commit", commit=sha)
    return models.RepoCommitResult(commit=sha)


@router.get("/projects/{project}/git/branches", operation_id="listGitBranches")
def list_branches(project: str, core: CoreDep) -> models.GitBranches:
    """로컬 브랜치와 메인 체크아웃의 현재 브랜치."""
    _, repo = _repo(core, project, None)
    try:
        return models.GitBranches(
            current=git.current_branch(repo), branches=git.branches(repo)
        )
    except git.GitError as exc:
        raise _git_failed(exc) from exc


@router.get(
    "/projects/{project}/git/worktrees", operation_id="listGitWorktrees"
)
def list_worktrees(project: str, core: CoreDep) -> list[models.GitWorktree]:
    """메인 체크아웃과 페이지 워크트리. 페이지 워크트리에는 페이지 id가 있다."""
    found, repo = _repo(core, project, None)
    try:
        trees = worktree.list_worktrees(repo)
    except git.GitError as exc:
        raise _git_failed(exc) from exc
    pages = {
        worktree_path(found.root, p.name).resolve(): p.name
        for p in (found.pages_dir.iterdir() if found.pages_dir.is_dir() else ())
    }
    return [
        models.GitWorktree(
            path=str(tree.path),
            branch=tree.branch,
            head=tree.head,
            main=tree.path.resolve() == found.root.resolve(),
            page=pages.get(tree.path.resolve()),
        )
        for tree in trees
    ]


@router.get("/projects/{project}/git/log", operation_id="getGitLog")
def get_log(
    project: str,
    core: CoreDep,
    page: PageQuery = None,
    ref: str = "HEAD",
    limit: Annotated[int, Query(ge=1, le=500)] = LOG_LIMIT,
) -> list[models.GitLogEntry]:
    """``ref``에서 거슬러 올라가는 커밋, 최근 것부터."""
    _, repo = _repo(core, project, page)
    try:
        commits = git.log(repo, ref, limit)
    except git.GitError as exc:
        raise errors.not_found(str(exc)) from exc
    return [
        models.GitLogEntry(
            hash=c.hash, author=c.author, date=c.date, subject=c.subject
        )
        for c in commits
    ]


@router.post("/projects/{project}/git/push", operation_id="pushGit")
def push(
    project: str, core: CoreDep, page: PageQuery = None
) -> models.RepoPushResult:
    """현재 브랜치를 같은 이름의 원격 브랜치로 강제 없이 보낸다."""
    found, repo = _repo(core, project, page)
    return push_folder(core, found, repo)


def push_folder(
    core: Core, project: projects.Project, repo: Path
) -> models.RepoPushResult:
    """정책을 확인하고 ``repo``의 현재 브랜치를 push한다.

    Raises:
        HttpError: 정책이 막았거나(409 ``denied``) push할 수 없다(409).
    """
    branch = git.current_branch(repo) or "HEAD"
    workspace.allow(project, f"git push origin {branch}")
    try:
        remote, branch = coderepo.push_current(repo)
    except AgentError as exc:
        raise errors.conflict(str(exc)) from exc
    core.announce_git(project.id, repo, "push", branch=branch)
    return models.RepoPushResult(branch=branch, remote=remote)


@router.post("/projects/{project}/git/pull", operation_id="pullGit")
def pull(
    project: str, core: CoreDep, page: PageQuery = None
) -> models.GitStatus:
    """빨리 감기로만 당겨 온다. 갈라졌으면 409."""
    found, repo = _repo(core, project, page)
    workspace.allow(found, "git pull --ff-only")
    try:
        git.pull(repo)
        status = git_status(repo)
    except git.GitError as exc:
        raise _git_failed(exc) from exc
    core.announce_git(found.id, repo, "pull", head=status.head)
    return status


@router.post(
    "/projects/{project}/git/init", status_code=201, operation_id="initGit"
)
def init(project: str, core: CoreDep) -> models.GitStatus:
    """프로젝트 폴더를 git 저장소로 만든다. ``.madang/``은 커밋에서 뺀다."""
    found, folder = _folder(core, project, None)
    if git.is_work_tree(folder):
        raise errors.conflict(f"{folder} is already a git repository")
    workspace.allow(found, "git init")
    try:
        git.run(folder, "init", "-q")
        # 기록 폴더를 track 설정대로 .git/info/exclude에 더한다.
        projects.create_records(found.root)
        status = git_status(folder)
    except (git.GitError, OSError, ValueError) as exc:
        raise errors.conflict(f"cannot initialize git: {exc}") from exc
    core.announce_git(found.id, folder, "init")
    return status
