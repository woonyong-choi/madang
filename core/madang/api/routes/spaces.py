"""공간 경로: 목록, 생성, 수정, 삭제와 공간의 페이지 목록·생성."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Response

from madang.api import errors, events, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.api.routes.pages import page_detail
from madang.store import pages, spaces, summary
from madang.store.page import SPACE_FILE

router = Router(tags=["spaces"])


def _space(core: Core, slug: str) -> Path:
    try:
        return spaces.space_path(core.home, slug)
    except FileNotFoundError as exc:
        raise errors.not_found(str(exc)) from exc


def _announce(core: Core, kind: str, space: Path) -> dict[str, Any]:
    data = summary.space_summary(space)
    core.hub.emit(kind, {"space": data}, space=space.name)
    return data


@router.get("/spaces", operation_id="listSpaces")
def list_spaces(core: CoreDep) -> list[models.Space]:
    """공간 목록. 초기화 전의 앱 홈에는 공간이 없다."""
    return [
        models.Space.model_validate(summary.space_summary(space))
        for space in summary.space_dirs(core.home)
    ]


@router.post("/spaces", status_code=201, operation_id="createSpace")
def create_space(body: models.SpaceCreate, core: CoreDep) -> models.Space:
    """공간을 만들고 커밋한다."""
    core.config()
    settings = body.model_dump(exclude={"slug", "title"}, exclude_none=True)
    with core.lock:
        try:
            space = spaces.create(core.home, body.slug, body.title, settings)
        except FileNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc
        except FileExistsError as exc:
            raise errors.conflict(str(exc)) from exc
        except ValueError as exc:
            raise errors.invalid(str(exc)) from exc
        core.commit([space], f"[{body.slug}] create space")
    return models.Space.model_validate(
        _announce(core, events.SPACE_CREATED, space)
    )


@router.patch("/spaces/{space}", operation_id="updateSpace")
def update_space(
    space: str, body: models.SpaceUpdate, core: CoreDep
) -> models.Space:
    """공간의 제목과 설정을 바꾸고 커밋한다."""
    folder = _space(core, space)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and not changes["title"]:
        raise errors.invalid("title cannot be empty")
    with core.lock:
        try:
            spaces.update(core.home, space, changes)
        except FileNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc
        except spaces.SpaceError as exc:
            raise errors.invalid(str(exc)) from exc
        core.commit([folder / SPACE_FILE], f"[{space}] edit space")
    return models.Space.model_validate(
        _announce(core, events.SPACE_UPDATED, folder)
    )


@router.delete("/spaces/{space}", status_code=204, operation_id="deleteSpace")
def delete_space(space: str, core: CoreDep) -> Response:
    """빈 공간을 지우고 커밋한다."""
    _space(core, space)
    with core.lock:
        try:
            removed = spaces.delete(core.home, space)
        except spaces.SpaceError as exc:
            raise errors.conflict(str(exc)) from exc
        core.commit(removed, f"[{space}] delete space")
    core.hub.emit(events.SPACE_DELETED, {"id": space}, space=space)
    return Response(status_code=204)


@router.get("/spaces/{space}/pages", tags=["pages"], operation_id="listPages")
def list_pages(space: str, core: CoreDep) -> list[models.PageCard]:
    """공간의 페이지 카드. 고정이 먼저, 그다음 공간의 정렬 기준."""
    folder = _space(core, space)
    cards = [summary.page_card(p) for p in summary.page_dirs(folder)]
    order = summary.space_summary(folder)["sort"]
    return [
        models.PageCard.model_validate(card)
        for card in summary.sort_cards(cards, order)
    ]


@router.post(
    "/spaces/{space}/pages",
    status_code=201,
    tags=["pages"],
    operation_id="createPage",
)
def create_page(
    space: str, body: models.PageCreate, core: CoreDep
) -> models.PageDetail:
    """페이지를 만들고 커밋한다."""
    cfg = core.config()
    _space(core, space)
    kind = body.kind or cfg.routes.default_kind
    if kind not in cfg.routes.kinds:
        raise errors.invalid(f"unknown kind '{kind}'")
    if not body.title.strip():
        raise errors.invalid("title cannot be empty")
    with core.lock:
        try:
            page_dir = pages.create_page(
                core.home, space, body.title, kind=kind
            )
        except FileExistsError as exc:
            raise errors.conflict(str(exc)) from exc
        core.commit([page_dir], f"[{page_dir.name}] create page")
    core.announce_page(page_dir, events.PAGE_CREATED)
    return page_detail(core, page_dir)
