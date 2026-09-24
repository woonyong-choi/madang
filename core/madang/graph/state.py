"""흐름 그래프의 상태: 흐름 제어 값만 담는다. 문서 내용은 넣지 않는다."""

from __future__ import annotations

from typing import Any, TypedDict


class FlowState(TypedDict):
    """메시지 하나를 처리하는 흐름의 상태.

    ``space``, ``page``, ``message``는 id다. 본문은 페이지 파일에서 읽는다.
    ``target``은 ``{block, elements, mode}``이다. ``result_status``는
    마지막 판정(done | blocked | review | doing | cancelled)이며 판정 전에는
    빈 문자열이다. ``last_run_kind``는 마지막으로 실행한 종류로, 리뷰
    실행이면 ``review``다. 보정 실행은 보정한 실행의 종류를 그대로 둔다.
    ``pending_decision``은 사람에게 묻는 동안만 채워진다.
    """

    space: str
    page: str
    message: str
    target: dict[str, Any]
    kind: str
    tier: int
    attempts: int
    runner: str
    model: str
    effort: str
    run_n: int
    result_status: str
    runs_this_message: int
    last_run_kind: str
    pending_decision: dict[str, Any] | None


def initial_state(
    space: str, page: str, message: str, target: dict[str, Any]
) -> FlowState:
    """새 메시지의 첫 상태를 반환한다.

    Args:
        space: 공간 슬러그.
        page: 페이지 id.
        message: 요청 메시지 블록 id.
        target: ``{block, elements, mode}``.

    Returns:
        1단계에서 시작하는 상태.
    """
    return FlowState(
        space=space,
        page=page,
        message=message,
        target=target,
        kind="",
        tier=1,
        attempts=0,
        runner="",
        model="",
        effort="",
        run_n=0,
        result_status="",
        runs_this_message=0,
        last_run_kind="",
        pending_decision=None,
    )
