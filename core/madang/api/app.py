"""FastAPI 앱 조립.

계약이 먼저다. ``/openapi.json``은 FastAPI가 만든 스키마가 아니라
``openapi.yaml`` 계약을 그대로 돌려준다. 구현이 계약을 따르는지는 테스트가
FastAPI가 만든 스키마와 계약을 비교해 확인한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from madang import __version__
from madang.api import errors
from madang.api.availability import Probe, probe_cli
from madang.api.contract import contract_document
from madang.api.core import Core
from madang.api.guard import LocalOnly
from madang.api.routes import (
    agent,
    files,
    git,
    messages,
    pages,
    projects,
    publish,
    runs,
    settings,
    system,
    viewers,
)
from madang.graph.nodes import RunnerFactory

ROUTERS = (
    system.router,
    settings.router,
    projects.router,
    pages.router,
    messages.router,
    files.router,
    git.router,
    runs.router,
    publish.router,
    viewers.router,
    agent.router,
)


def create_app(
    home: Path,
    *,
    runners: RunnerFactory | None = None,
    probe: Probe = probe_cli,
    core_url: str | None = None,
    claude_dir: Path | None = None,
    codex_dir: Path | None = None,
) -> FastAPI:
    """앱 홈 하나를 맡는 core API 앱을 만든다.

    Args:
        home: 앱 홈. 아직 없어도 된다(``POST /home``으로 만든다).
        runners: 러너 이름으로 러너를 만든다. 기본은 config.yaml의 runners 절.
        probe: 러너 사용 가능 여부 확인.
        core_url: 에이전트에 넘길 core 주소.
        claude_dir: 사용량을 읽을 Claude Code 폴더. 기본은 ``~/.claude``.
        codex_dir: 사용량을 읽을 Codex 폴더. 기본은 ``~/.codex``.

    Returns:
        FastAPI 앱. ``app.state.core``에 ``Core``가 있다.
    """
    app = FastAPI(
        title="Madang core API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        separate_input_output_schemas=False,
    )
    app.state.core = Core(
        home,
        runners=runners,
        probe=probe,
        core_url=core_url,
        claude_dir=claude_dir,
        codex_dir=codex_dir,
    )
    app.add_middleware(LocalOnly)
    errors.install(app)
    for router in ROUTERS:
        app.include_router(router)
    app.openapi = contract_document  # type: ignore[method-assign]
    return app


def generated_openapi(app: FastAPI) -> dict[str, Any]:
    """구현(경로와 모델)에서 FastAPI가 만든 OpenAPI 문서를 반환한다.

    계약과 비교하는 데 쓴다. WebSocket 경로는 들어가지 않는다.
    """
    return get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        separate_input_output_schemas=False,
    )
