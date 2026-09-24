"""파일 경로: 미등록 파일, 휴지통, 템플릿."""

from __future__ import annotations

from fastapi import Path as PathParam

from madang.api import errors, events, models
from madang.api.routes import CoreDep, Router
from madang.store import blocks, git, pages, templates, trash
from madang.store import unknown_files as unknown

router = Router()

_COMMIT_MESSAGES = {
    "artifact": "edit state.md",
    "keep": "edit page.md",
}


@router.get(
    "/pages/{page}/unknown-files",
    tags=["files"],
    operation_id="listUnknownFiles",
)
def list_unknown_files(page: str, core: CoreDep) -> list[models.UnknownFile]:
    """실행이 남겼지만 등록하지 않은 파일."""
    page_dir = core.page_dir(page)
    return [
        models.UnknownFile.model_validate(item)
        for item in unknown.list_unknown(page_dir)
    ]


@router.post(
    "/pages/{page}/unknown-files/{path:path}",
    tags=["files"],
    operation_id="resolveUnknownFile",
)
def resolve_unknown_file(
    page: str,
    path: str,
    body: models.UnknownFileAction,
    core: CoreDep,
) -> list[models.UnknownFile]:
    """미등록 파일 하나를 등록·유지·삭제하고 남은 목록을 돌려준다."""
    page_dir = core.page_dir(page)
    with core.lock:
        try:
            touched = unknown.resolve(page_dir, core.home, path, body.action)
        except LookupError as exc:
            raise errors.not_found(str(exc)) from exc
        if touched:
            message = _COMMIT_MESSAGES.get(body.action, f"delete {path}")
            if body.action == "delete":
                core.commit(touched, f"[{page}] {message}")
            else:
                core.page_commit(page_dir, message)
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return [
        models.UnknownFile.model_validate(item)
        for item in unknown.list_unknown(page_dir)
    ]


# 휴지통


@router.get("/trash", tags=["trash"], operation_id="listTrash")
def list_trash(core: CoreDep) -> list[models.TrashEntry]:
    """최근 삭제된 페이지와 블록, 최신순."""
    return [
        models.TrashEntry.model_validate(entry.to_dict())
        for entry in trash.list_trash(core.home)
    ]


@router.post(
    "/trash/{commit}/restore", tags=["trash"], operation_id="restoreTrash"
)
def restore_trash(commit: str, core: CoreDep) -> models.TrashRestore:
    """삭제 커밋이 지운 것을 되살리고 커밋한다."""
    core.config()
    with core.lock:
        try:
            entry = trash.find(core.home, commit)
            sha = trash.restore(core.home, entry)
        except LookupError as exc:
            raise errors.not_found(str(exc)) from exc
        except (trash.TrashError, git.GitError) as exc:
            raise errors.conflict(str(exc)) from exc
    page_dir = (
        core.home
        / pages.SPACES_DIR
        / entry.space
        / pages.PAGES_DIR
        / entry.page
    )
    if entry.block is None:
        core.announce_page(page_dir, events.PAGE_CREATED)
    else:
        header = blocks.block_header(page_dir, entry.block)
        core.announce_block(page_dir, events.BLOCK_ADDED, header)
        core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.TrashRestore(commit=sha, paths=entry.paths)


# 템플릿


@router.get("/templates", tags=["templates"], operation_id="listTemplates")
def list_templates(core: CoreDep) -> list[models.Template]:
    """내장·설치된 view 템플릿."""
    return [
        models.Template.model_validate(item)
        for item in templates.list_templates(core.home)
    ]


@router.get(
    "/templates/{name}/schema",
    tags=["templates"],
    operation_id="getTemplateSchema",
)
def get_template_schema(
    core: CoreDep, name: str = PathParam()
) -> models.TemplateSchema:
    """템플릿의 슬롯 스키마(schema.json)."""
    found = templates.template_schema(core.home, name)
    if found is None:
        raise errors.not_found(f"template '{name}' has no schema")
    return models.TemplateSchema.model_validate(found)
