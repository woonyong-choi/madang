"""페이지 경로: 페이지, 블록, 메모리.

편집은 커밋 하나가 된다: ``[<page-id>] edit <block>``,
``[<page-id>] delete <block|page>``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import Response

from madang.api import errors, events, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.cli_agent import ops
from madang.cli_agent.context import AgentError, PageContext
from madang.store import blocks, frontmatter, git, pages, summary, trash
from madang.store import unknown_files as unknown
from madang.store.files import atomic_write
from madang.store.page import SPACE_FILE, STATE_FILE, space_dir, space_repo
from madang.validate import count_tokens, validate_state

router = Router()
ROOT_FILE = "root.md"
LAYERS = ("root", "space", "state")


def page_detail(core: Core, page_dir: Path) -> models.PageDetail:
    """페이지 상세(미등록 파일과 기다리는 결정 포함)를 반환한다."""
    detail = summary.page_detail(page_dir)
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
    """제목, 고정, 태그, 블록 순서를 바꾸거나 다른 공간으로 옮긴다."""
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
        target = changes.pop("space", None)
        if changes:
            pages.update_page(page_dir, lambda h: h.update(changes))
            core.page_commit(page_dir, "edit page")
        if target is not None and target != page_dir.parent.parent.name:
            page_dir = _move(core, page_dir, target)
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.PageCard.model_validate(summary.page_card(page_dir))


def _move(core: Core, page_dir: Path, space: str) -> Path:
    _idle(core, page_dir)
    old = core.rel(page_dir)
    try:
        moved = pages.move_page(core.home, page_dir, space)
    except FileNotFoundError as exc:
        raise errors.not_found(str(exc)) from exc
    except FileExistsError as exc:
        raise errors.conflict(str(exc)) from exc
    core.commit([old, moved], f"[{moved.name}] move to {space}")
    return moved


@router.delete(
    "/pages/{page}", status_code=204, tags=["pages"], operation_id="deletePage"
)
def delete_page(page: str, core: CoreDep) -> Response:
    """페이지 폴더를 지우고 커밋한다. 휴지통에서 되살릴 수 있다."""
    page_dir = core.page_dir(page)
    _idle(core, page_dir)
    space = page_dir.parent.parent.name
    with core.lock:
        rel = core.rel(page_dir)
        git.run(core.home, "rm", "-r", "-q", "--ignore-unmatch", "--", rel)
        _remove_tree(page_dir)
        core.commit([rel], trash.delete_message(page, trash.DELETE_PAGE))
    core.hub.emit(events.PAGE_DELETED, {"id": page}, space=space, page=page)
    return Response(status_code=204)


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


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
        core.page_commit(page_dir, f"add {block_id}")
    header = blocks.block_header(page_dir, block_id)
    core.announce_block(page_dir, events.BLOCK_ADDED, header)
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.BlockHeader.model_validate(header)


def _create_view(core: Core, page_dir: Path, body: models.BlockCreate) -> str:
    if not body.template:
        raise errors.invalid("view block needs a template")
    ctx = PageContext(
        home=core.home, page_dir=page_dir, from_env=False, cfg=core.config()
    )
    data = [f"{slot}={b}" for slot, b in (body.bindings or {}).items()]
    try:
        ops.create_view(ctx, body.template, data, title=body.name)
    except AgentError as exc:
        issues = getattr(exc, "issues", ())
        raise errors.invalid(str(exc), issues) from exc
    order = pages.read_header(page_dir / "page.md").get("blocks") or []
    return str(order[-1])


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
    """블록 파일 전체를 바꾸고 커밋한다."""
    page_dir = core.page_dir(page)
    found = _file_block(page_dir, block)
    with core.lock:
        try:
            blocks.write_content(found, body.content)
        except blocks.BlockContentError as exc:
            raise errors.invalid(str(exc), exc.issues) from exc
        core.page_commit(page_dir, f"edit {block}")
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
    """머리부 키만 바꾸고 커밋한다."""
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
        core.page_commit(page_dir, f"edit {block}")
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
    """``git rm``으로 블록을 지우고 커밋한다.

    메시지는 log.md에 기록으로 남기고 page.md 순서에서만 뺀다.
    """
    page_dir = core.page_dir(page)
    _block_or_404(page_dir, block)
    found = blocks.find_file_block(page_dir, block)
    _idle(core, page_dir)
    with core.lock:
        rels = [core.rel(p) for p in found.files()] if found else []
        if rels:
            git.run(
                core.home, "rm", "-q", "-f", "--ignore-unmatch", "--", *rels
            )
        for path in found.files() if found else []:
            path.unlink(missing_ok=True)
        blocks.remove_from_order(page_dir, block)
        core.commit(
            [*rels, core.rel(page_dir / "page.md")],
            trash.delete_message(page, block),
        )
    core.hub.emit(
        events.BLOCK_DELETED,
        {"id": block},
        space=page_dir.parent.parent.name,
        page=page,
        block=block,
    )
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return Response(status_code=204)


# 메모리


def _memory_path(core: Core, page_dir: Path, layer: str) -> Path:
    if layer == "root":
        return core.home / ROOT_FILE
    if layer == "space":
        space = space_dir(page_dir)
        assert space is not None  # find_page가 공간 안의 페이지만 찾는다
        return space / SPACE_FILE
    return page_dir / STATE_FILE


def _memory_file(
    core: Core, page_dir: Path, layer: str, limit: int
) -> dict[str, Any]:
    path = _memory_path(core, page_dir, layer)
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {
        "layer": layer,
        "path": core.rel(path),
        "content": content,
        "tokens": count_tokens(content),
        "token_limit": limit if layer == "state" else None,
    }


@router.get("/pages/{page}/memory", tags=["memory"], operation_id="getMemory")
def get_memory(page: str, core: CoreDep) -> models.Memory:
    """root.md, space.md, state.md."""
    page_dir = core.page_dir(page)
    limit = core.config().madang.limits.state_tokens
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
    """메모리 파일 하나를 검사해 저장하고 커밋한다."""
    page_dir = core.page_dir(page)
    cfg = core.config()
    path = _memory_path(core, page_dir, layer)
    with core.lock:
        if layer == "state":
            _check_state(page_dir, body.content, cfg)
        else:
            _check_front_matter(path, body.content)
        atomic_write(path, body.content)
        if layer == "state":
            core.page_commit(page_dir, f"edit {STATE_FILE}")
        else:
            scope = "home" if layer == "root" else path.parent.name
            core.commit([path], f"[{scope}] edit {path.name}")
    limit = cfg.madang.limits.state_tokens
    saved = _memory_file(core, page_dir, layer, limit)
    core.announce_memory(layer, saved["tokens"], page_dir)
    if layer == "state":
        core.announce_page(page_dir, events.PAGE_UPDATED)
    elif layer == "space":
        space = path.parent
        core.hub.emit(
            events.SPACE_UPDATED,
            {"space": summary.space_summary(space)},
            space=space.name,
        )
    return models.MemoryFile.model_validate(saved)


def _check_state(page_dir: Path, content: str, cfg: Any) -> None:
    probe = page_dir / f".{STATE_FILE}.check"
    probe.write_text(content, encoding="utf-8")
    try:
        issues = validate_state(
            probe,
            repo=space_repo(page_dir),
            token_limit=cfg.madang.limits.state_tokens,
            kinds=cfg.routes.kinds,
        )
    finally:
        os.unlink(probe)
    if issues:
        found = [
            {**errors.issue_dict(issue), "path": STATE_FILE} for issue in issues
        ]
        raise errors.ValidationFailureError(
            f"{STATE_FILE} failed validation", found
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
