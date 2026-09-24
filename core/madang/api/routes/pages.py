"""페이지 경로: 페이지, 블록, 메모리.

core는 페이지 파일을 커밋하지 않는다. 지운 페이지와 블록은 프로젝트의
``.madang/trash/``로 옮겨 두고 휴지통에서 되살린다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Response

from madang.api import errors, events, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.cli_agent import views
from madang.cli_agent.context import AgentError, PageContext
from madang.store import blocks, frontmatter, pages, summary, trash
from madang.store import unknown_files as unknown
from madang.store.files import atomic_write
from madang.store.home import PROFILE_FILE
from madang.store.page import LEDGER_FILE, project_root
from madang.validate import count_tokens, validate_ledger

router = Router()
# REST 계약의 메모리 층 이름. root는 Profile, project는 Brief, state는
# Ledger 파일이다.
LAYERS = ("root", "project", "state")
PROFILE_LAYER, BRIEF_LAYER, LEDGER_LAYER = LAYERS


def page_detail(core: Core, page_dir: Path) -> models.PageDetail:
    """페이지 상세(미등록 파일과 기다리는 결정 포함)를 반환한다."""
    detail = summary.page_detail(page_dir, core.project_of(page_dir).id)
    detail["unknown_files"] = unknown.list_unknown(page_dir)
    waiting = core.flows.waiting(page_dir)
    if waiting is not None:
        detail["waiting"] = waiting
    return models.PageDetail.model_validate(detail)


def _idle(core: Core, page_dir: Path) -> None:
    if core.flows.busy(page_dir.name):
        raise errors.conflict(
            f"a flow is running on page '{page_dir.name}'", errors.BUSY
        )


# 페이지


@router.get("/pages/{page}", tags=["pages"], operation_id="getPage")
def get_page(page: str, core: CoreDep) -> models.PageDetail:
    """page.md와 블록 머리부."""
    return page_detail(core, core.page_dir(page))


@router.patch("/pages/{page}", tags=["pages"], operation_id="updatePage")
def update_page(
    page: str, body: models.PageUpdate, core: CoreDep
) -> models.PageCard:
    """제목, 고정, 태그, 블록 순서를 바꾸거나 다른 프로젝트로 옮긴다."""
    page_dir = core.page_dir(page)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "title" in changes and not changes["title"].strip():
        raise errors.invalid("title cannot be empty")
    with core.lock:
        header = pages.read_header(page_dir / "page.md")
        order = changes.pop("blocks_order", None)
        if order is not None:
            current = [str(b) for b in header.get("blocks") or []]
            if sorted(order) != sorted(current):
                raise errors.invalid(
                    "blocks_order must list exactly the page's blocks"
                )
            changes["blocks"] = order
        target = changes.pop("project", None)
        if changes:
            pages.update_page(page_dir, lambda h: h.update(changes))
        if target is not None and target != core.project_of(page_dir).id:
            page_dir = _move(core, page_dir, target)
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.PageCard.model_validate(core.page_card(page_dir))


def _move(core: Core, page_dir: Path, project: str) -> Path:
    _idle(core, page_dir)
    target = core.project(project)
    target.pages_dir.mkdir(parents=True, exist_ok=True)
    try:
        return pages.move_page(page_dir, target.pages_dir)
    except FileNotFoundError as exc:
        raise errors.not_found(str(exc)) from exc
    except FileExistsError as exc:
        raise errors.conflict(str(exc)) from exc


@router.delete(
    "/pages/{page}", status_code=204, tags=["pages"], operation_id="deletePage"
)
def delete_page(page: str, core: CoreDep) -> Response:
    """페이지 폴더를 휴지통으로 옮긴다. 휴지통에서 되살릴 수 있다."""
    page_dir = core.page_dir(page)
    _idle(core, page_dir)
    project = core.project_of(page_dir)
    with core.lock:
        trash.delete_page(project, page_dir)
    core.hub.emit(
        events.PAGE_DELETED, {"id": page}, project=project.id, page=page
    )
    return Response(status_code=204)


# 블록


def _block_or_404(page_dir: Path, block: str) -> dict[str, Any]:
    try:
        return blocks.block_header(page_dir, block)
    except blocks.BlockNotFoundError as exc:
        raise errors.not_found(str(exc)) from exc


def _file_block(page_dir: Path, block: str) -> blocks.FileBlock:
    found = blocks.find_file_block(page_dir, block)
    if found is not None:
        return found
    _block_or_404(page_dir, block)
    raise errors.invalid(
        f"block '{block}' is a message; messages cannot be edited"
    )


@router.post(
    "/pages/{page}/blocks",
    status_code=201,
    tags=["blocks"],
    operation_id="createBlock",
)
def create_block(
    page: str, body: models.BlockCreate, core: CoreDep
) -> models.BlockHeader:
    """doc, data, view 블록을 만들어 페이지 끝에 붙인다."""
    page_dir = core.page_dir(page)
    if pages.slugify(body.name) != body.name:
        raise errors.invalid(f"name '{body.name}' is not a slug")
    with core.lock:
        if body.type == "view":
            block_id = _create_view(core, page_dir, body)
        else:
            if body.content is None:
                raise errors.invalid(f"{body.type} block needs content")
            try:
                block_id = blocks.create_file_block(
                    page_dir,
                    body.type,
                    body.name,
                    body.content,
                    body.format or "json",
                )
            except blocks.BlockContentError as exc:
                raise errors.invalid(str(exc), exc.issues) from exc
    header = blocks.block_header(page_dir, block_id)
    core.announce_block(page_dir, events.BLOCK_ADDED, header)
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.BlockHeader.model_validate(header)


def _create_view(core: Core, page_dir: Path, body: models.BlockCreate) -> str:
    if not body.template:
        raise errors.invalid("view block needs a template")
    ctx = PageContext(home=core.home, page_dir=page_dir, cfg=core.config())
    data = [f"{slot}={b}" for slot, b in (body.bindings or {}).items()]
    data += body.data or []
    try:
        return views.create_view(
            ctx,
            body.template,
            data,
            title=body.title,
            run=core.active_run(page_dir, in_run=body.in_run),
        )
    except (AgentError, frontmatter.FrontmatterError) as exc:
        issues = getattr(exc, "issues", ())
        raise errors.invalid(str(exc), issues) from exc


@router.get(
    "/pages/{page}/blocks/{block}", tags=["blocks"], operation_id="getBlock"
)
def get_block(page: str, block: str, core: CoreDep) -> models.Block:
    """블록 파일 전체."""
    page_dir = core.page_dir(page)
    header = _block_or_404(page_dir, block)
    found = blocks.find_file_block(page_dir, block)
    content = (
        found.path.read_text(encoding="utf-8")
        if found is not None
        else header["text"]
    )
    return models.Block.model_validate({"header": header, "content": content})


@router.put(
    "/pages/{page}/blocks/{block}", tags=["blocks"], operation_id="replaceBlock"
)
def replace_block(
    page: str, block: str, body: models.BlockContent, core: CoreDep
) -> models.Block:
    """블록 파일 전체를 바꾼다."""
    page_dir = core.page_dir(page)
    found = _file_block(page_dir, block)
    with core.lock:
        try:
            blocks.write_content(found, body.content)
        except blocks.BlockContentError as exc:
            raise errors.invalid(str(exc), exc.issues) from exc
    header = blocks.block_header(page_dir, block)
    core.announce_block(page_dir, events.BLOCK_UPDATED, header)
    return models.Block.model_validate(
        {"header": header, "content": body.content}
    )


@router.patch(
    "/pages/{page}/blocks/{block}",
    tags=["blocks"],
    operation_id="updateBlockHeader",
)
def update_block_header(
    page: str, block: str, body: models.BlockHeaderPatch, core: CoreDep
) -> models.BlockHeader:
    """머리부 키만 바꾼다."""
    page_dir = core.page_dir(page)
    found = _file_block(page_dir, block)
    changes = body.model_dump(exclude_unset=True)
    with core.lock:
        stored = blocks.read_header(found)
        merged = {**stored, **changes}
        _check_header(page_dir, merged)

        def mutate(header: dict[str, Any]) -> None:
            for key, value in changes.items():
                if value is None:
                    header.pop(key, None)
                else:
                    header[key] = value

        blocks.update_header(found, mutate)
    header = blocks.block_header(page_dir, block)
    core.announce_block(page_dir, events.BLOCK_UPDATED, header)
    return models.BlockHeader.model_validate(header)


def _check_header(page_dir: Path, header: dict[str, Any]) -> None:
    presets = header.get("presets") or {}
    active = header.get("active_preset")
    if active is not None and active not in presets:
        raise errors.invalid(f"active_preset '{active}' is not in presets")
    bound = [*(header.get("bindings") or {}).values()]
    for preset in presets.values():
        bound += list((preset or {}).values())
    missing = sorted(
        {str(b) for b in bound if not pages.block_files(page_dir, str(b))}
    )
    if missing:
        raise errors.invalid(f"bound blocks not found: {', '.join(missing)}")


@router.delete(
    "/pages/{page}/blocks/{block}",
    status_code=204,
    tags=["blocks"],
    operation_id="deleteBlock",
)
def delete_block(page: str, block: str, core: CoreDep) -> Response:
    """블록 파일을 휴지통으로 옮기고 page.md 순서에서 뺀다.

    메시지는 log.md에 기록으로 남기고 page.md 순서에서만 뺀다.
    """
    page_dir = core.page_dir(page)
    _block_or_404(page_dir, block)
    found = blocks.find_file_block(page_dir, block)
    _idle(core, page_dir)
    project = core.project_of(page_dir)
    with core.lock:
        files = found.files() if found else []
        trash.delete_block(project, page_dir, block, files)
    core.hub.emit(
        events.BLOCK_DELETED,
        {"id": block},
        project=project.id,
        page=page,
        block=block,
    )
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return Response(status_code=204)


# 메모리


def _memory_path(core: Core, page_dir: Path, layer: str) -> Path:
    if layer == PROFILE_LAYER:
        return core.home / PROFILE_FILE
    if layer == BRIEF_LAYER:
        return core.project_of(page_dir).brief
    return page_dir / LEDGER_FILE


def _memory_file(
    core: Core, page_dir: Path, layer: str, limit: int
) -> dict[str, Any]:
    path = _memory_path(core, page_dir, layer)
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {
        "layer": layer,
        "path": str(path),
        "content": content,
        "tokens": count_tokens(content),
        "token_limit": limit if layer == LEDGER_LAYER else None,
    }


@router.get("/pages/{page}/memory", tags=["memory"], operation_id="getMemory")
def get_memory(page: str, core: CoreDep) -> models.Memory:
    """profile.md, brief.md, ledger.md."""
    page_dir = core.page_dir(page)
    limit = core.config().madang.limits.ledger_tokens
    return models.Memory.model_validate(
        {layer: _memory_file(core, page_dir, layer, limit) for layer in LAYERS}
    )


@router.put(
    "/pages/{page}/memory/{layer}", tags=["memory"], operation_id="saveMemory"
)
def save_memory(
    page: str,
    layer: models.MemoryLayer,
    body: models.MemoryContent,
    core: CoreDep,
) -> models.MemoryFile:
    """메모리 파일 하나를 검사해 저장한다."""
    page_dir = core.page_dir(page)
    cfg = core.config()
    path = _memory_path(core, page_dir, layer)
    with core.lock:
        if layer == LEDGER_LAYER:
            _check_ledger(page_dir, body.content, cfg)
        else:
            _check_front_matter(path, body.content)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, body.content)
    limit = cfg.madang.limits.ledger_tokens
    saved = _memory_file(core, page_dir, layer, limit)
    core.announce_memory(layer, saved["tokens"], page_dir)
    if layer == LEDGER_LAYER:
        core.announce_page(page_dir, events.PAGE_UPDATED)
    elif layer == BRIEF_LAYER:
        project = core.project_of(page_dir)
        core.hub.emit(
            events.PROJECT_UPDATED,
            {"project": summary.project_summary(project)},
            project=project.id,
        )
    return models.MemoryFile.model_validate(saved)


def _check_ledger(page_dir: Path, content: str, cfg: Any) -> None:
    probe = page_dir / f".{LEDGER_FILE}.check"
    probe.write_text(content, encoding="utf-8")
    try:
        issues = validate_ledger(
            probe,
            repo=project_root(page_dir),
            token_limit=cfg.madang.limits.ledger_tokens,
            kinds=cfg.routes.kinds,
        )
    finally:
        os.unlink(probe)
    if issues:
        found = [
            {**errors.issue_dict(issue), "path": LEDGER_FILE}
            for issue in issues
        ]
        raise errors.ValidationFailureError(
            f"{LEDGER_FILE} failed validation", found
        )


def _check_front_matter(path: Path, content: str) -> None:
    try:
        frontmatter.load_header(frontmatter.split(content))
    except frontmatter.FrontmatterError as exc:
        issue = {
            "code": "frontmatter",
            "message": str(exc),
            "line": exc.line,
            "path": path.name,
        }
        raise errors.ValidationFailureError(
            f"{path.name} failed validation", [issue]
        ) from exc
