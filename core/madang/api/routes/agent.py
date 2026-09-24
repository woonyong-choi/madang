"""에이전트 경로: madang CLI 명령이 부르는 ledger.md·프로젝트 저장소 변경.

ledger.md를 고친 뒤에는 페이지를 검사하고, 실패하면 되돌린 뒤 400을
돌려준다. 커밋과 push는 정책(``policy.deny``)을 지나 core ``git`` 모듈로
한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Body

from madang import git, recorder
from madang.api import errors, events, models, workspace
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.api.routes.git import push_folder
from madang.cli_agent import artifacts, decisions, tasks
from madang.cli_agent import repo as coderepo
from madang.cli_agent.context import AgentError, PageContext
from madang.recorder.undo import COMMIT
from madang.store import frontmatter, pages
from madang.store.page import LEDGER_FILE

router = Router(tags=["agent"])


def _context(core: Core, page_dir: Path) -> PageContext:
    return PageContext(home=core.home, page_dir=page_dir, cfg=core.config())


def _rejected(exc: Exception) -> Exception:
    issues = getattr(exc, "issues", None)
    if issues:
        return errors.invalid(str(exc), issues)
    return errors.invalid(str(exc))


def _state_changed(core: Core, page_dir: Path) -> None:
    core.announce_page(page_dir, events.PAGE_UPDATED)


def _state_list(page_dir: Path, key: str) -> list[Any]:
    items = pages.read_header(page_dir / LEDGER_FILE).get(key)
    return list(items) if isinstance(items, list) else []


@router.patch("/pages/{page}/ledger/tasks", operation_id="setTask")
def set_task(page: str, body: models.TaskUpdate, core: CoreDep) -> models.Task:
    """ledger.md에 작업을 추가하거나 갱신한다."""
    page_dir = core.page_dir(page)
    with core.lock:
        try:
            tasks.set_task(
                _context(core, page_dir),
                body.id,
                body.status,
                title=body.title,
                due=body.due,
            )
        except (AgentError, frontmatter.FrontmatterError) as exc:
            raise _rejected(exc) from exc
        _state_changed(core, page_dir)
    task = next(
        t
        for t in _state_list(page_dir, "tasks")
        if isinstance(t, dict) and str(t.get("id")) == body.id
    )
    if task.get("due") is not None:
        task = {**task, "due": str(task["due"])}
    return models.Task.model_validate(task)


@router.post(
    "/pages/{page}/ledger/decisions",
    status_code=201,
    operation_id="recordDecision",
)
def record_decision(
    page: str, body: models.DecisionCreate, core: CoreDep
) -> models.LedgerDecision:
    """ledger.md에 결정을 기록한다."""
    page_dir = core.page_dir(page)
    with core.lock:
        try:
            decisions.decide(
                _context(core, page_dir),
                body.id,
                topic=body.topic,
                choice=body.choice,
                options=body.options,
                by=body.by or "human",
                run=core.active_run(page_dir, in_run=body.in_run),
                supersedes=body.supersedes,
                state=body.state or "confirmed",
            )
        except (AgentError, frontmatter.FrontmatterError) as exc:
            raise _rejected(exc) from exc
        _state_changed(core, page_dir)
    decision = next(
        d
        for d in _state_list(page_dir, "decisions")
        if isinstance(d, dict) and str(d.get("id")) == body.id
    )
    return models.LedgerDecision.model_validate(decision)


@router.post("/pages/{page}/ledger/artifacts", operation_id="addArtifact")
def add_artifact(
    page: str, body: models.ArtifactAdd, core: CoreDep
) -> list[str]:
    """ledger.md의 artifacts에 파일을 등록한다."""
    page_dir = core.page_dir(page)
    with core.lock:
        try:
            artifacts.add_artifact(_context(core, page_dir), body.path)
        except (AgentError, frontmatter.FrontmatterError) as exc:
            raise _rejected(exc) from exc
        _state_changed(core, page_dir)
    return [str(a) for a in _state_list(page_dir, "artifacts")]


# 프로젝트 저장소


@router.post("/projects/{project}/repo/commit", operation_id="commitRepo")
def commit_repo(
    project: str, body: models.RepoCommit, core: CoreDep
) -> models.RepoCommitResult:
    """에이전트가 일한 작업 트리의 모든 변경을 커밋한다.

    ``page``에 워크트리가 있으면 그 워크트리(페이지 브랜치)에, 아니면
    프로젝트 폴더에 커밋한다. 실행 안에서 온 요청이면 그 실행의 되돌리기
    기록에 커밋을 남긴다.
    """
    core.config()
    found = core.project(project)
    page_dir = workspace.page_in(core, found, body.page)
    repo = workspace.require_repo(workspace.work_folder(found, page_dir))
    workspace.allow(found, "git commit")
    before = _head(repo)
    try:
        short = coderepo.commit_all(repo, body.message)
        sha = git.rev_parse(repo)
    except (AgentError, git.GitError) as exc:
        raise errors.conflict(str(exc)) from exc
    run = (
        core.active_run(page_dir, in_run=body.in_run)
        if page_dir is not None
        else None
    )
    if page_dir is not None and run is not None and before is not None:
        with core.lock:
            recorder.record_git(page_dir, run, COMMIT, repo, before, sha)
    core.announce_git(found.id, repo, "commit", commit=sha)
    return models.RepoCommitResult(commit=short)


@router.post("/projects/{project}/repo/push", operation_id="pushRepo")
def push_repo(
    project: str,
    core: CoreDep,
    body: Annotated[models.RepoPush, Body(default_factory=models.RepoPush)],
) -> models.RepoPushResult:
    """에이전트가 일한 작업 트리의 현재 브랜치를 정책을 지나 push한다."""
    core.config()
    found = core.project(project)
    page_dir = workspace.page_in(core, found, body.page)
    repo = workspace.require_repo(workspace.work_folder(found, page_dir))
    return push_folder(core, found, repo)


def _head(repo: Path) -> str | None:
    try:
        return git.rev_parse(repo)
    except git.GitError:
        return None  # 아직 커밋이 없다
