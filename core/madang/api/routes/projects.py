"""프로젝트 경로: 목록, 등록, 수정, 등록 해제와 프로젝트의 페이지 목록·생성."""

from __future__ import annotations

from pathlib import Path

from fastapi import Response

from madang import config
from madang.api import errors, events, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.api.routes.pages import page_detail
from madang.store import pages, projects, summary

router = Router(tags=["projects"])


def _announce(
    core: Core, kind: str, project: projects.Project
) -> models.Project:
    data = summary.project_summary(project)
    core.hub.emit(kind, {"project": data}, project=project.id)
    return models.Project.model_validate(data)


@router.get("/projects", operation_id="listProjects")
def list_projects(core: CoreDep) -> list[models.Project]:
    """프로젝트 목록(등록 순서). 초기화 전의 앱 홈에는 프로젝트가 없다."""
    return [
        models.Project.model_validate(summary.project_summary(project))
        for project in projects.load(core.home)
    ]


@router.post("/projects", status_code=201, operation_id="createProject")
def create_project(body: models.ProjectCreate, core: CoreDep) -> models.Project:
    """폴더를 프로젝트로 등록하고 ``.madang/``을 만든다."""
    core.config()
    if not body.path.strip():
        raise errors.invalid("path is empty")
    settings = body.model_dump(
        include=set(projects.SETTINGS), exclude_none=True
    )
    with core.lock:
        try:
            project = projects.add(
                core.home,
                Path(body.path),
                project_id=body.id,
                title=body.title,
                settings=settings,
            )
        except FileNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc
        except FileExistsError as exc:
            raise errors.conflict(str(exc)) from exc
        except (projects.ProjectError, config.ConfigError) as exc:
            raise errors.invalid(str(exc)) from exc
    return _announce(core, events.PROJECT_CREATED, project)


@router.patch("/projects/{project}", operation_id="updateProject")
def update_project(
    project: str, body: models.ProjectUpdate, core: CoreDep
) -> models.Project:
    """프로젝트의 제목과 표시 설정을 바꾼다."""
    core.project(project)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and not changes["title"]:
        raise errors.invalid("title cannot be empty")
    with core.lock:
        try:
            updated = projects.update(core.home, project, changes)
        except FileNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc
        except projects.ProjectError as exc:
            raise errors.invalid(str(exc)) from exc
    return _announce(core, events.PROJECT_UPDATED, updated)


@router.delete(
    "/projects/{project}", status_code=204, operation_id="deleteProject"
)
def delete_project(project: str, core: CoreDep) -> Response:
    """프로젝트 등록을 지운다. 폴더와 ``.madang/``은 그대로 둔다."""
    core.project(project)
    with core.lock:
        try:
            projects.remove(core.home, project)
        except projects.ProjectError as exc:
            raise errors.conflict(str(exc)) from exc
    core.hub.emit(events.PROJECT_DELETED, {"id": project}, project=project)
    return Response(status_code=204)


@router.get(
    "/projects/{project}/pages", tags=["pages"], operation_id="listPages"
)
def list_pages(project: str, core: CoreDep) -> list[models.PageCard]:
    """프로젝트의 페이지 카드. 고정이 먼저, 그다음 프로젝트의 정렬 기준."""
    found = core.project(project)
    cards = [
        summary.page_card(p, found.id)
        for p in summary.page_dirs(found.pages_dir)
    ]
    order = summary.project_summary(found)["sort"]
    return [
        models.PageCard.model_validate(card)
        for card in summary.sort_cards(cards, order)
    ]


@router.post(
    "/projects/{project}/pages",
    status_code=201,
    tags=["pages"],
    operation_id="createPage",
)
def create_page(
    project: str, body: models.PageCreate, core: CoreDep
) -> models.PageDetail:
    """프로젝트의 ``.madang/pages/``에 페이지를 만든다."""
    cfg = core.config()
    found = core.project(project)
    kind = body.kind or cfg.routes.default_kind
    if kind not in cfg.routes.kinds:
        raise errors.invalid(f"unknown kind '{kind}'")
    if not body.title.strip():
        raise errors.invalid("title cannot be empty")
    if not found.root.is_dir():
        raise errors.conflict(f"project folder {found.root} does not exist")
    with core.lock:
        found.pages_dir.mkdir(parents=True, exist_ok=True)
        try:
            page_dir = pages.create_page(found.pages_dir, body.title, kind=kind)
        except FileExistsError as exc:
            raise errors.conflict(str(exc)) from exc
    core.announce_page(page_dir, events.PAGE_CREATED)
    return page_detail(core, page_dir)
