"""``madang decide``: state.md에 결정을 기록한다."""

from __future__ import annotations

from typing import Any

from madang.cli_agent.context import AgentError, PageContext, guarded
from madang.cli_agent.items import check_id, find_by_id, items_of
from madang.store import pages
from madang.store.page import STATE_FILE

DECISION_STATES = ("proposed", "confirmed", "superseded", "deferred")


def decide(
    ctx: PageContext,
    decision_id: str,
    *,
    topic: str,
    choice: str,
    options: list[str],
    by: str,
    run: int | None = None,
    supersedes: str | None = None,
    state: str = "confirmed",
) -> None:
    """state.md에 새 결정을 기록한다.

    Args:
        ctx: 변경할 페이지.
        decision_id: 새 결정의 id.
        topic: 무엇을 결정했는지.
        choice: 선택한 옵션. ``options`` 중 하나여야 한다.
        options: 선택 가능한 옵션. 비어 있거나 중복이 있으면 안 된다.
        by: 결정한 사람.
        run: 결정이 나온 실행 번호. 실행 밖이면 None.
        supersedes: 이 결정이 대체하는 기존 결정의 id.
        state: 결정 상태. ``DECISION_STATES`` 중 하나.

    Raises:
        AgentError: 인자가 잘못됐거나, id가 이미 있거나, 페이지 검증에
            실패했다.
    """
    check_id(decision_id, "결정")
    opts = [o.strip() for o in options if o.strip()]
    if not opts:
        raise AgentError("options에 값이 하나 이상 있어야 한다(a,b,c)")
    if len(set(opts)) != len(opts):
        raise AgentError("options에 중복된 값이 있다")
    if choice not in opts:
        raise AgentError(
            f"choice '{choice}'가 options({', '.join(opts)})에 없다"
        )
    if state not in DECISION_STATES:
        raise AgentError(
            f"state '{state}'는 {' | '.join(DECISION_STATES)} 중 하나여야 한다"
        )
    if supersedes == decision_id:
        raise AgentError("결정은 자기 자신을 대체할 수 없다")

    def mutate(header: dict[str, Any]) -> None:
        decisions = items_of(header, "decisions")
        if find_by_id(decisions, decision_id) is not None:
            raise AgentError(
                f"결정 '{decision_id}'가 이미 있다. 새 id로 기록하고 "
                "supersedes를 지정한다"
            )
        if supersedes is not None:
            old = find_by_id(decisions, supersedes)
            if old is None:
                raise AgentError(f"대체할 결정 '{supersedes}'가 없다")
            old["state"] = "superseded"
        decisions.append(
            {
                "id": decision_id,
                "topic": topic,
                "choice": choice,
                "options": opts,
                "by": by,
                "run": run,
                "state": state,
                "supersedes": supersedes,
            }
        )
        header["decisions"] = decisions

    with guarded(ctx, ctx.page_dir / STATE_FILE):
        pages.update_state(ctx.page_dir, mutate)
