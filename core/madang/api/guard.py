"""로컬 전용 가드: 브라우저 페이지와 DNS 리바인딩을 막는다.

core는 127.0.0.1에만 묶이지만, 사용자의 브라우저에 열린 다른 사이트도
127.0.0.1로 요청을 보낼 수 있다. 그래서 ``Host``가 로컬 이름이 아니거나,
``Origin``이 있는데 로컬이 아니면 HTTP와 WebSocket 모두 403으로 끊는다.
앱(Ktor)과 madang CLI는 ``Origin``을 보내지 않는다.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _host_name(value: str) -> str:
    return (urlsplit(f"//{value}").hostname or "").lower()


def is_local(headers: Headers) -> bool:
    """요청 머리의 ``Host``와 ``Origin``이 모두 로컬인지 반환한다."""
    if _host_name(headers.get("host", "")) not in LOCAL_HOSTS:
        return False
    origin = headers.get("origin")
    if origin is None:
        return True
    return (urlsplit(origin).hostname or "").lower() in LOCAL_HOSTS


class LocalOnly:
    """로컬이 아닌 요청을 403으로 끊는 ASGI 미들웨어."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> Any:
        """``http``와 ``websocket`` 요청의 머리를 보고 통과시키거나 끊는다."""
        if scope["type"] not in ("http", "websocket") or is_local(
            Headers(scope=scope)
        ):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = {"error": "forbidden", "message": "only local clients"}
        await JSONResponse(body, status_code=403)(scope, receive, send)
