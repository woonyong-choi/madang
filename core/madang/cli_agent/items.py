"""state.md 항목(태스크·결정·산출물)을 다루는 공통 도우미."""

from __future__ import annotations

import re
from typing import Any

from madang.cli_agent.context import AgentError

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def is_valid_id(value: str) -> bool:
    """``value``가 태스크·결정·템플릿 id로 쓸 수 있는 이름인지 반환한다."""
    return bool(_ID.match(value))


def check_id(value: str, what: str) -> None:
    """이름 형식을 검사한다.

    Args:
        value: 검사할 id.
        what: 오류 메시지에 쓸 종류 이름. 예: ``태스크``.

    Raises:
        AgentError: 형식이 올바르지 않다.
    """
    if not is_valid_id(value):
        raise AgentError(f"잘못된 {what} id '{value}'")


def items_of(header: dict[str, Any], key: str) -> list[Any]:
    """머리부의 ``key`` 목록을 반환한다. 없으면 빈 목록.

    Raises:
        AgentError: 값이 목록이 아니다.
    """
    value = header.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise AgentError(f"state.md의 '{key}'가 목록이 아니다")
    return value


def find_by_id(items: list[Any], item_id: str) -> dict[str, Any] | None:
    """``id``가 ``item_id``인 항목을 반환한다. 없으면 None."""
    return next(
        (
            item
            for item in items
            if isinstance(item, dict) and str(item.get("id")) == item_id
        ),
        None,
    )
