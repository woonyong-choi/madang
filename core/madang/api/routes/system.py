"""시스템·설정 경로: 상태, 러너, 사용량, 앱 홈, 라우팅 표, 이벤트 스트림."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Query, WebSocket, WebSocketDisconnect

from madang import __version__, config
from madang.api import errors, models, usage
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.store.files import atomic_write
from madang.store.home import NotAHomeError, init_home
from madang.validate.routes import validate_routes

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


@router.get("/usage", tags=["runners"], operation_id="getUsage")
def get_usage(
    core: CoreDep,
    days: Annotated[
        int, Query(ge=1, le=90, description="오늘을 포함해 셀 날 수.")
    ] = usage.DEFAULT_DAYS,
) -> models.Usage:
    """구독 도구의 토큰 사용(Claude Code 대화 기록)."""
    checked = datetime.now().astimezone().replace(microsecond=0)
    since = checked.date() - timedelta(days=days - 1)
    return models.Usage.model_validate(
        {
            "checked": checked,
            "since": since.isoformat(),
            "tools": [usage.claude_usage(core.claude_dir, since)],
        }
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
    """앱 홈(profile.md, config.yaml, viewers.yaml, cache/)을 만들어 쓴다."""
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
    """config.yaml의 routes 절 원문."""
    core.config()
    text = config.section_text(_settings_text(core), config.ROUTES_KEY)
    if text is None:
        text = config.section_text(
            config.default_text(config.CONFIG_FILE), config.ROUTES_KEY
        )
    return models.RoutesDocument(text=text or "")


@router.put("/config/routes", tags=["setup"], operation_id="saveRoutes")
def save_routes(
    body: models.RoutesDocument, core: CoreDep
) -> models.RoutesDocument:
    """config.yaml의 routes 절을 검사해 바꾼다. 다른 절과 주석은 그대로다."""
    cfg = core.config()
    issues = validate_routes(body.text, cfg.runners)
    if issues:
        raise errors.invalid("routes failed validation", issues)
    with core.lock:
        text = config.replace_section(
            _settings_text(core), config.ROUTES_KEY, body.text
        )
        path = core.home / config.CONFIG_FILE
        try:
            config.parse_config(core.home, path, text)
        except config.ConfigError as exc:
            raise errors.invalid(f"routes cannot be saved: {exc}") from exc
        atomic_write(path, text)
    return models.RoutesDocument(text=body.text)


def _settings_text(core: Core) -> str:
    return (core.home / config.CONFIG_FILE).read_text(encoding="utf-8")


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
