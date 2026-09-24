"""러너 대체표와 조기 실패 규칙: config.yaml ``routes`` 절의 두 키.

``fallbacks``는 ``러너/모델``을 쓸 수 없을 때 대신 쓸 ``러너/모델``이고,
``early_failure``는 실행이 시작하자마자 도구 문제로 끝났는지 가리는 규칙이다.
절에 키가 없으면 번들된 기본값을 쓴다. 추론 강도는 대체해도 그대로다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from madang.config import ROUTES_KEY, RoutesConfig, default_data
from madang.runners.base import RunResult

FALLBACKS_KEY = "fallbacks"
EARLY_FAILURE_KEY = "early_failure"
# 쓸 수 없어서 바꿨을 때의 이유. 조기 실패면 일치한 패턴이 이유다.
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Route:
    """실행 하나의 러너, 모델, 추론 강도."""

    runner: str
    model: str
    effort: str

    @property
    def key(self) -> str:
        """대체표와 이벤트에 쓰는 ``러너/모델``."""
        return f"{self.runner}/{self.model}"


class EarlyFailure(BaseModel):
    """시작 직후 실패를 도구 문제로 보는 규칙."""

    model_config = ConfigDict(extra="forbid")

    within_seconds: float = 90.0
    patterns: list[str] = Field(default_factory=list)


class _Settings(BaseModel):
    fallbacks: dict[str, str] = Field(default_factory=dict)
    early_failure: EarlyFailure = Field(default_factory=EarlyFailure)


@dataclass(frozen=True)
class Fallbacks:
    """대체표와 조기 실패 규칙.

    Attributes:
        table: ``러너/모델`` -> 대신 쓸 ``러너/모델``.
        early_failure: 조기 실패 규칙.
    """

    table: dict[str, str]
    early_failure: EarlyFailure

    @classmethod
    def from_routes(cls, routes: RoutesConfig) -> Fallbacks:
        """``routes`` 절에서 읽는다. 빠진 키는 번들된 기본값으로 채운다.

        Args:
            routes: 읽은 라우팅 표.

        Returns:
            대체 규칙.

        Raises:
            ValueError: 값의 형식이 맞지 않는 경우.
        """
        bundled = default_data().get(ROUTES_KEY) or {}
        given = routes.model_extra or {}
        data: dict[str, Any] = {
            key: given[key] if key in given else bundled.get(key)
            for key in (FALLBACKS_KEY, EARLY_FAILURE_KEY)
        }
        try:
            settings = _Settings.model_validate(
                {k: v for k, v in data.items() if v is not None}
            )
        except ValidationError as exc:
            raise ValueError(f"routes fallbacks are invalid: {exc}") from exc
        for source, target in settings.fallbacks.items():
            for value in (source, target):
                if value.count("/") != 1 or "" in value.split("/"):
                    raise ValueError(
                        f"routes fallbacks entry {value!r} is not runner/model"
                    )
        return cls(settings.fallbacks, settings.early_failure)

    def replacement(self, route: Route) -> Route | None:
        """``route`` 대신 쓸 경로. 대체표에 없으면 None.

        Args:
            route: 쓸 수 없는 경로.

        Returns:
            같은 추론 강도의 대체 경로.
        """
        target = self.table.get(route.key)
        if target is None:
            return None
        runner, model = target.split("/")
        return Route(runner, model, route.effort)

    def early_failure_reason(self, result: RunResult) -> str | None:
        """실행이 조기 실패였으면 일치한 패턴을, 아니면 None을 반환한다.

        오류로 끝났고, 제한 시간 안에 끝났고, 오류 문구에 패턴이 들어 있어야
        조기 실패다. 대소문자는 가리지 않는다.

        Args:
            result: 끝난 실행.

        Returns:
            일치한 패턴.
        """
        rule = self.early_failure
        if result.status != "error" or result.duration > rule.within_seconds:
            return None
        text = (result.error or "").lower()
        for pattern in rule.patterns:
            if pattern.lower() in text:
                return pattern
        return None
