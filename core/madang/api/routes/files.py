"""파일 경로: 파일 트리, 미등록 파일, 휴지통, 템플릿."""

from __future__ import annotations

from typing import Annotated

from fastapi import Path as PathParam
from fastapi import Query

from madang import config, git
from madang import runs as targets
from madang.api import errors, events, filetree, models, workspace
from madang.api.routes import CoreDep, Router
from madang.store import blocks, projects, templates, trash
from madang.store import unknown_files as unknown

router = Router()


@router.get(
    "/projects/{project}/files", tags=["files"], operation_id="listFiles"
)
def list_files(
    project: str,
    core: CoreDep,
    lens: models.FileLens = "all",
    page: Annotated[
        str | None,
        Query(description="이 페이지의 워크트리(있으면)와 기록을 쓴다."),
    ] = None,
) -> models.FileTree:
    """작업 폴더의 파일 트리. 렌즈: 전체, 이 페이지, 변경됨."""
    found = core.project(project)
    page_dir = workspace.page_in(core, found, page)
    folder = workspace.work_folder(found, page_dir)
    changes: dict[str, str] | None = None
    try:
        if lens == "page":
            if page_dir is None:
                raise errors.invalid("lens 'page' needs a page")
            files = filetree.page_files(page_dir, folder)
        elif lens == "changed":
            changes = filetree.changed_files(workspace.require_repo(folder))
            files = sorted(changes)
        else:
            files = filetree.all_files(folder)
        declared = targets.targets(found.root)
    except git.GitError as exc:
        raise errors.conflict(str(exc)) from exc
    except (OSError, config.ConfigError) as exc:
        raise errors.invalid(f"cannot list files: {exc}") from exc
    entries, root_runs, truncated = filetree.tree(files, declared, changes)
    return models.FileTree(
        root=str(folder),
        lens=lens,
        entries=[models.FileEntry.model_validate(e) for e in entries],
        runs=root_runs,
        truncated=truncated,
    )


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
            unknown.resolve(page_dir, path, body.action)
        except LookupError as exc:
            raise errors.not_found(str(exc)) from exc
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return [
        models.UnknownFile.model_validate(item)
        for item in unknown.list_unknown(page_dir)
    ]


# 휴지통


@router.get("/trash", tags=["trash"], operation_id="listTrash")
def list_trash(core: CoreDep) -> list[models.TrashEntry]:
    """모든 프로젝트의 최근 삭제된 페이지와 블록, 최신순."""
    return [
        models.TrashEntry.model_validate(entry.to_dict())
        for entry in trash.list_trash(projects.load(core.home))
    ]


@router.post("/trash/{id}/restore", tags=["trash"], operation_id="restoreTrash")
def restore_trash(id: str, core: CoreDep) -> models.TrashRestore:
    """휴지통 항목을 원래 자리로 되돌려 옮긴다."""
    core.config()
    with core.lock:
        try:
            project, entry = trash.find(projects.load(core.home), id)
            page_dir = trash.restore(project, entry)
        except LookupError as exc:
            raise errors.not_found(str(exc)) from exc
        except trash.TrashError as exc:
            raise errors.conflict(str(exc)) from exc
    if entry.block is None:
        core.announce_page(page_dir, events.PAGE_CREATED)
    else:
        header = blocks.block_header(page_dir, entry.block)
        core.announce_block(page_dir, events.BLOCK_ADDED, header)
        core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.TrashRestore(id=entry.id, paths=entry.paths)


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
