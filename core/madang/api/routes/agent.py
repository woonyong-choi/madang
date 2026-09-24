"""에이전트 경로: madang CLI 명령이 부르는 state.md·코드 저장소 변경.

state.md를 고친 뒤에는 페이지를 검사하고, 실패하면 되돌린 뒤 400을
돌려준다. 흐름이 그 페이지를 실행 중이면 앱 홈은 커밋하지 않는다(실행
커밋에 들어간다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from madang.api import errors, events, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.cli_agent import artifacts, decisions, promote, tasks
from madang.cli_agent import repo as coderepo
from madang.cli_agent.context import AgentError, PageContext
from madang.store import frontmatter, pages, spaces
from madang.store.page import STATE_FILE

router = Router(tags=["agent"])


def _context(core: Core, page_dir: Path) -> PageContext:
    return PageContext(home=core.home, page_dir=page_dir, cfg=core.config())


def _rejected(exc: Exception) -> Exception:
    issues = getattr(exc, "issues", None)
    if issues:
        return errors.invalid(str(exc), issues)
    return errors.invalid(str(exc))


def _state_changed(core: Core, page_dir: Path) -> None:
    core.page_commit(page_dir, f"edit {STATE_FILE}")
    core.announce_page(page_dir, events.PAGE_UPDATED)


def _state_list(page_dir: Path, key: str) -> list[Any]:
    items = pages.read_header(page_dir / STATE_FILE).get(key)
    return list(items) if isinstance(items, list) else []


@router.patch("/pages/{page}/state/tasks", operation_id="setTask")
def set_task(page: str, body: models.TaskUpdate, core: CoreDep) -> models.Task:
    """state.md에 작업을 추가하거나 갱신한다."""
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
    "/pages/{page}/state/decisions",
    status_code=201,
    operation_id="recordDecision",
)
def record_decision(
    page: str, body: models.DecisionCreate, core: CoreDep
) -> models.StateDecision:
    """state.md에 결정을 기록한다."""
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
                run=core.active_run(page_dir),
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
    return models.StateDecision.model_validate(decision)


@router.post("/pages/{page}/state/artifacts", operation_id="addArtifact")
def add_artifact(
    page: str, body: models.ArtifactAdd, core: CoreDep
) -> list[str]:
    """state.md의 artifacts에 파일을 등록한다."""
    page_dir = core.page_dir(page)
    with core.lock:
        try:
            artifacts.add_artifact(_context(core, page_dir), body.path)
        except (AgentError, frontmatter.FrontmatterError) as exc:
            raise _rejected(exc) from exc
        _state_changed(core, page_dir)
    return [str(a) for a in _state_list(page_dir, "artifacts")]


# 코드 저장소


def _space_page(core: Core, slug: str) -> PageContext:
    """코드 저장소 명령에 쓸 공간의 문맥. 페이지는 공간 폴더로 대신한다."""
    cfg = core.config()
    try:
        space = spaces.space_path(core.home, slug)
    except FileNotFoundError as exc:
        raise errors.not_found(str(exc)) from exc
    # 저장소는 space.md만 보므로 공간 안의 가상 페이지 경로로 충분하다.
    probe = space / pages.PAGES_DIR / "_"
    return PageContext(home=core.home, page_dir=probe, cfg=cfg)


def _require_repo(ctx: PageContext) -> Path:
    try:
        return coderepo.require_repo(ctx)
    except AgentError as exc:
        raise errors.conflict(str(exc), errors.NO_REPO) from exc


@router.post("/spaces/{space}/repo/commit", operation_id="commitRepo")
def commit_repo(
    space: str, body: models.RepoCommit, core: CoreDep
) -> models.RepoCommitResult:
    """공간의 코드 저장소에 모든 변경을 커밋한다."""
    repo = _require_repo(_space_page(core, space))
    try:
        sha = coderepo.commit_all(repo, body.message)
    except AgentError as exc:
        raise errors.conflict(str(exc)) from exc
    return models.RepoCommitResult(commit=sha)


@router.post("/spaces/{space}/repo/push", operation_id="pushRepo")
def push_repo(space: str, core: CoreDep) -> models.RepoPushResult:
    """코드 저장소의 현재 브랜치를 강제 없이 push한다."""
    repo = _require_repo(_space_page(core, space))
    try:
        remote, branch = coderepo.push_current(repo)
    except AgentError as exc:
        raise errors.conflict(str(exc)) from exc
    return models.RepoPushResult(branch=branch, remote=remote)


@router.post(
    "/pages/{page}/blocks/{block}/promote",
    tags=["blocks"],
    operation_id="promoteBlock",
)
def promote_block(page: str, block: str, core: CoreDep) -> models.PromoteResult:
    """블록 파일을 코드 저장소 docs/에 복사하고 커밋한다."""
    page_dir = core.page_dir(page)
    if not pages.block_files(page_dir, block):
        raise errors.not_found(f"block '{block}' has no file in blocks/")
    ctx = _context(core, page_dir)
    _require_repo(ctx)
    with core.lock:
        try:
            promoted = promote.promote(ctx, block)
        except AgentError as exc:
            raise errors.conflict(str(exc)) from exc
        _state_changed(core, page_dir)
    return models.PromoteResult(path=promoted.path, commit=promoted.commit)
