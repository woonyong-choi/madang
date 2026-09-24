"""뷰어 경로: 등록부(``viewers.yaml``) 목록·상태와 등록.

뷰어는 원래 자리에 둔 폴더이고 등록은 그 폴더를 가리키는 참조다. 정본
폴더가 없으면 상태가 ``broken``(끊김)이다. 등록이나 live 뷰어의 변경은
``viewer.changed``로 알린다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Query

from madang import viewers
from madang.api import errors, events, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router

router = Router(tags=["viewers"])

_CONFLICTS = ("name-conflict",)


def _registered(
    registry: viewers.Registry, entry: viewers.Registration
) -> models.ViewerStatus:
    status = registry.status(entry)
    version = None
    if status == viewers.STATUS_OK:
        try:
            version = viewers.load_manifest(entry.source).version
        except viewers.ViewerError:
            status = viewers.STATUS_BROKEN
    return models.ViewerStatus(
        name=entry.name,
        source=str(entry.source),
        follow=entry.follow,
        pinned=entry.pinned,
        status=status,
        scope="registry",
        version=version,
    )


def _rejected(exc: viewers.ViewerError) -> Exception:
    if exc.code in _CONFLICTS:
        return errors.conflict(str(exc))
    return errors.invalid(str(exc))


@router.get("/viewers", operation_id="listViewers")
def list_viewers(
    core: CoreDep,
    project: Annotated[
        str | None,
        Query(description="이 프로젝트의 `.madang/viewers/` 뷰어도 넣는다."),
    ] = None,
) -> list[models.ViewerStatus]:
    """등록된 뷰어와 상태. ``project``를 주면 그 프로젝트 전용 뷰어가 먼저다."""
    registry = viewers.Registry(core.home)
    found: list[models.ViewerStatus] = []
    try:
        if project is not None:
            root = core.project(project).root
            found += [
                models.ViewerStatus(
                    name=name,
                    source=str(manifest.folder),
                    follow=viewers.FOLLOW_LIVE,
                    status=viewers.STATUS_OK,
                    scope="project",
                    project=project,
                    version=manifest.version,
                )
                for name, manifest in viewers.project_viewers(root).items()
            ]
        found += [_registered(registry, e) for e in registry.entries()]
    except viewers.ViewerError as exc:
        raise errors.conflict(str(exc)) from exc
    return found


@router.post("/viewers", status_code=201, operation_id="registerViewer")
def register_viewer(
    body: models.ViewerRegister, core: CoreDep
) -> models.ViewerStatus:
    """뷰어 폴더를 ``viewer.json``의 이름으로 등록한다. 복사하지 않는다.

    ``pinned``면 지금 내용의 해시로 캐시 사본을 만든다.
    """
    core.config()
    registry = viewers.Registry(core.home)
    with core.lock:
        try:
            entry = registry.register(body.source, body.follow)
        except viewers.ViewerError as exc:
            raise _rejected(exc) from exc
    status = _registered(registry, entry)
    announce_viewer(core, entry.name, status.status)
    return status


def announce_viewer(core: Core, name: str, status: str) -> None:
    """``viewer.changed``를 낸다."""
    core.hub.emit(events.VIEWER_CHANGED, {"name": name, "status": status})
