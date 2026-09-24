"""``madang task``: ledger.md의 태스크를 추가하거나 갱신한다."""

from __future__ import annotations

from datetime import date
from typing import Any

from madang.cli_agent.context import AgentError, PageContext, guarded
from madang.cli_agent.items import check_id, find_by_id, items_of
from madang.store import pages
from madang.store.page import LEDGER_FILE

TASK_STATUSES = ("todo", "doing", "blocked", "review", "done")


def set_task(
    ctx: PageContext,
    task_id: str,
    status: str,
    title: str | None = None,
    due: str | None = None,
) -> None:
    """ledger.md에 태스크를 추가하거나 기존 태스크를 갱신한다.

    Args:
        ctx: 변경할 페이지.
        task_id: 태스크 id.
        status: 새 상태. ``TASK_STATUSES`` 중 하나.
        title: 태스크 제목. 새 태스크는 필수.
        due: 마감일. ``YYYY-MM-DD``.

    Raises:
        AgentError: 인자가 잘못됐거나 페이지 검증에 실패했다.
    """
    check_id(task_id, "태스크")
    if status not in TASK_STATUSES:
        raise AgentError(
            f"status '{status}'는 {' | '.join(TASK_STATUSES)} 중 하나여야 한다"
        )
    due_date: date | None = None
    if due is not None:
        try:
            due_date = date.fromisoformat(due)
        except ValueError as exc:
            raise AgentError(f"due '{due}'는 YYYY-MM-DD 날짜가 아니다") from exc

    def mutate(header: dict[str, Any]) -> None:
        tasks = items_of(header, "tasks")
        task = find_by_id(tasks, task_id)
        if task is None:
            if not title:
                raise AgentError(
                    f"태스크 '{task_id}'가 없다. 새로 만들려면 title이 필요하다"
                )
            task = {"id": task_id, "title": title, "status": status}
            tasks.append(task)
        else:
            task["status"] = status
            if title:
                task["title"] = title
        if due_date is not None:
            task["due"] = due_date
        header["tasks"] = tasks

    with guarded(ctx, ctx.page_dir / LEDGER_FILE):
        pages.update_state(ctx.page_dir, mutate)
