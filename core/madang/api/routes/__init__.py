"""API 경로 묶음. 응답에서 값이 없는 선택 키는 빼고 보낸다."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from madang.api.core import Core


class Router(APIRouter):
    """응답 모델의 None 값을 빼고 직렬화하는 라우터.

    계약은 없는 선택 키를 "없음"으로 읽으므로 ``null``을 보내지 않는다.
    """

    def add_api_route(self, path: str, endpoint: Any, **kwargs: Any) -> None:
        """``response_model_exclude_none``을 켠 채로 경로를 더한다.

        데코레이터는 이 인자를 늘 명시해 넘기므로 덮어쓴다.
        """
        kwargs["response_model_exclude_none"] = True
        super().add_api_route(path, endpoint, **kwargs)


def get_core(request: Request) -> Core:
    """앱에 붙은 ``Core``를 반환한다."""
    return request.app.state.core


CoreDep = Annotated[Core, Depends(get_core)]
