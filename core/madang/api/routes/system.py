"""시스템·설정 경로: 상태, 러너, 앱 홈, 라우팅 표, 이벤트 스트림."""

from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from madang import __version__, config
from madang.api import errors, models
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.store.files import atomic_write
from madang.store.home import NotAHomeError, init_home
from madang.validate.routes import ROUTES_PATH, validate_routes

router = Router()


@router.get("/health", tags=["system"], operation_id="getHealth")
def get_health() -> models.Health:
    """core가 떠 있는지 알린다."""
    return models.Health(status="ok", version=__version__)


@router.get("/runners", tags=["runners"], operation_id="listRunners")
def list_runners(core: CoreDep) -> models.RunnerAvailability:
    """러너별 사용 가능 여부(5분 캐시)."""
    cfg = config.load_config(core.home)
    return models.RunnerAvailability.model_validate(
        core.availability.get(cfg.runners)
    )


# 앱 홈


def _home_status(core: Core) -> models.HomeStatus:
    return models.HomeStatus(path=str(core.home), initialized=core.initialized)


@router.get("/home", tags=["setup"], operation_id="getHome")
def get_home(core: CoreDep) -> models.HomeStatus:
    """core가 쓰는 앱 홈(전역 설정 폴더)과 초기화 여부."""
    return _home_status(core)


@router.post("/home", tags=["setup"], operation_id="initHome")
def init_app_home(body: models.HomeInit, core: CoreDep) -> models.HomeStatus:
    """앱 홈에 전역 설정과 root.md를 만들고 core가 그 홈을 쓰게 한다."""
    if not body.path.strip():
        raise errors.invalid("path is empty")
    path = config.resolve_home(body.path)
    with core.lock:
        try:
            init_home(path)
        except NotAHomeError as exc:
            raise errors.conflict(str(exc)) from exc
        except OSError as exc:
            raise errors.conflict(f"cannot initialize {path}: {exc}") from exc
        core.switch_home(path)
    return _home_status(core)


@router.get("/config/routes", tags=["setup"], operation_id="getRoutes")
def get_routes(core: CoreDep) -> models.RoutesDocument:
    """config/routes.yaml 원문."""
    core.config()
    path = core.home / ROUTES_PATH
    text = (
        path.read_text(encoding="utf-8")
        if path.is_file()
        else config.default_text("routes.yaml")
    )
    return models.RoutesDocument(text=text)


@router.put("/config/routes", tags=["setup"], operation_id="saveRoutes")
def save_routes(
    body: models.RoutesDocument, core: CoreDep
) -> models.RoutesDocument:
    """config/routes.yaml을 검사해 저장한다."""
    cfg = core.config()
    issues = validate_routes(body.text, cfg.runners)
    if issues:
        raise errors.invalid("routes.yaml failed validation", issues)
    with core.lock:
        atomic_write(core.home / ROUTES_PATH, body.text)
    return models.RoutesDocument(text=body.text)


# 이벤트


@router.websocket("/events")
async def open_events(websocket: WebSocket) -> None:
    """변경 이벤트 스트림. 서버만 보낸다."""
    core: Core = websocket.app.state.core
    queue = core.hub.subscribe()
    await websocket.accept()
    receiver = asyncio.ensure_future(websocket.receive())
    try:
        while True:
            getter = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait(
                {getter, receiver}, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done:
                await websocket.send_json(getter.result())
            else:
                getter.cancel()
            if receiver in done:
                if receiver.result()["type"] == "websocket.disconnect":
                    break
                receiver = asyncio.ensure_future(websocket.receive())
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel()
        core.hub.unsubscribe(queue)
