"""메시지와 실행 경로: 메시지, 실행 기록·이벤트·취소·되돌리기, 답, 입력 추정."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Query, Response

from madang import recorder
from madang.api import errors, events, models
from madang.api.routes import CoreDep, Router
from madang.assemble import assemble
from madang.deciders import Question, build_chain, target_kind
from madang.graph.nodes import resolve_route
from madang.runners import make_runner
from madang.runners.base import RunEvent, StreamParser
from madang.store import pages, runs, summary
from madang.store.page import LEDGER_FILE

router = Router()


@router.post(
    "/pages/{page}/messages",
    status_code=202,
    tags=["messages"],
    operation_id="sendMessage",
)
def send_message(
    page: str, body: models.MessageCreate, core: CoreDep
) -> models.MessageAccepted:
    """메시지를 남기고 흐름을 백그라운드에서 시작한다."""
    page_dir = core.page_dir(page)
    if not body.text.strip():
        raise errors.invalid("text is empty")
    target = body.target.model_dump(exclude_none=True) if body.target else None
    message = core.flows.start(page_dir, body.text, target)
    return models.MessageAccepted(message=message)


# 실행


def _record(page_dir: Any, n: int) -> runs.RunRecord:
    try:
        return runs.read_run(page_dir, n)
    except FileNotFoundError as exc:
        raise errors.not_found(f"run {n} not found") from exc
    except (OSError, ValueError) as exc:
        raise errors.conflict(f"run {n} cannot be read: {exc}") from exc


@router.get("/pages/{page}/runs/{n}", tags=["runs"], operation_id="getRun")
def get_run(page: str, n: int, core: CoreDep) -> models.RunRecord:
    """실행 기록(runs/N.json)."""
    page_dir = core.page_dir(page)
    record = _record(page_dir, n)
    return models.RunRecord.model_validate(summary.run_record(record))


@router.post(
    "/pages/{page}/runs/{n}/cancel",
    status_code=202,
    tags=["runs"],
    operation_id="cancelRun",
)
def cancel_run(page: str, n: int, core: CoreDep) -> Response:
    """진행 중인 실행을 멈춘다."""
    page_dir = core.page_dir(page)
    current = runs.current(page_dir)
    if current is None or not 1 <= n <= current:
        raise errors.not_found(f"run {n} not found")
    if not core.flows.cancel(page_dir, n):
        raise errors.conflict(f"run {n} is not in progress")
    return Response(status_code=202)


@router.get(
    "/pages/{page}/runs/{n}/events",
    tags=["runs"],
    operation_id="listRunEvents",
)
def list_run_events(
    page: str, n: int, core: CoreDep
) -> list[models.RunStreamEvent]:
    """실행의 이벤트를 도구에 중립인 형태로 도착 순서대로."""
    page_dir = core.page_dir(page)
    path = runs.events_path(page_dir, n)
    if not path.is_file():
        raise errors.not_found(f"run {n} not found")
    record = (
        runs.read_run(page_dir, n)
        if runs.record_path(page_dir, n).is_file()
        else None
    )
    runner = record.runner if record else core.flows.runner(page)
    try:
        parser = make_runner(runner or "", core.config()).new_parser()
    except ValueError:
        return []
    return [
        models.RunStreamEvent.model_validate(event)
        for event in _stream_events(path.read_text("utf-8"), parser, record)
    ]


def _stream_events(
    text: str, parser: StreamParser, record: runs.RunRecord | None
) -> list[dict[str, Any]]:
    """원본 스트림을 러너 파서로 다시 읽어 정규화한다.

    실행이 끝났으면 러너가 마지막에 내는 ``done`` 또는 ``error``를 붙인다.
    """
    found: list[RunEvent] = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            found += parser.feed(obj)
    if record is not None and record.finished is not None:
        if record.error and record.error != parser.error:
            found.append(RunEvent("error", message=record.error))
        elif not record.error:
            found.append(RunEvent("done", text=parser.final_text))
    return [event.to_dict() for event in found]


@router.post(
    "/pages/{page}/runs/{n}/undo", tags=["runs"], operation_id="undoRun"
)
def undo_run(page: str, n: int, core: CoreDep) -> models.UndoResult:
    """실행 하나의 부작용(게시, 머지·커밋, 페이지 파일)을 역순으로 되감는다.

    그 실행 뒤에 파일이 다시 바뀌었거나, 커밋이 이력에서 사라졌거나, 더
    나중 게시가 있으면 아무것도 바꾸지 않고 409로 거부한다.
    """
    page_dir = core.page_dir(page)
    _record(page_dir, n)
    if core.flows.busy(page):
        raise errors.conflict(
            f"a flow is running on page '{page}'", errors.BUSY
        )
    project = core.project_of(page_dir)
    with core.lock:
        try:
            result = recorder.undo(page_dir, n)
        except recorder.UndoError as exc:
            raise errors.conflict(str(exc)) from exc
    for commit in result.reverted:
        core.announce_git(project.id, project.root, "undo", commit=commit)
    for number in result.unpublished:
        core.hub.emit(
            events.PUBLISH_DONE,
            {"n": number, "undo": True},
            project=project.id,
            page=page,
            run=n,
        )
    core.announce_page(page_dir, events.PAGE_UPDATED)
    return models.UndoResult(
        run=n,
        restored=result.restored,
        skipped=result.skipped,
        reverted=result.reverted,
        unpublished=result.unpublished,
    )


# 결정과 묻는 블록


@router.post(
    "/pages/{page}/asks/{id}/answer",
    status_code=202,
    tags=["decisions"],
    operation_id="answerAsk",
)
def answer_ask(
    page: str, id: str, body: models.DecisionAnswer, core: CoreDep
) -> Response:
    """page.md의 묻는 블록 ``id``에 답하고 멈춘 흐름을 이어 간다."""
    page_dir = core.page_dir(page)
    core.flows.answer_ask(page_dir, id, body.choice)
    return Response(status_code=202)


@router.post(
    "/pages/{page}/decisions/{id}/answer",
    status_code=202,
    tags=["decisions"],
    operation_id="answerDecision",
)
def answer_decision(
    page: str, id: str, body: models.DecisionAnswer, core: CoreDep
) -> Response:
    """기다리는 흐름에 답하고 이어 간다."""
    page_dir = core.page_dir(page)
    core.flows.answer(page_dir, id, body.choice)
    return Response(status_code=202)


# 입력 미리보기


@router.get(
    "/pages/{page}/preview-input",
    tags=["messages"],
    operation_id="previewInput",
)
def preview_input(
    page: str,
    core: CoreDep,
    target: str | None = None,
    elements: Annotated[list[str] | None, Query()] = None,
    mode: models.TargetMode | None = None,
    text: str = "",
) -> models.InputPreview:
    """다음 호출의 라우팅과 부분별 토큰 추정. 실행하지 않는다."""
    page_dir = core.page_dir(page)
    cfg = core.config()
    chosen = {"block": target, "elements": elements or [], "mode": mode}
    kind = target_kind(chosen)
    if kind is None:
        page_kind = pages.page_kind(page_dir)
        decision = build_chain(cfg.routes).decide(
            Question(
                "choice", text, list(cfg.routes.kinds), page_kind=page_kind
            )
        )
        kind = (
            str(decision.choice)
            if decision
            else cfg.routes.default_for(page_kind)
        )
    tiers = cfg.routes.tiers.get(kind)
    if not tiers:
        raise errors.invalid(f"routes has no tiers for kind '{kind}'")
    owner = str(pages.read_header(page_dir / LEDGER_FILE).get("owner") or "")
    implementer = owner.split("/", 1)[0] or next(iter(cfg.runners), "")
    try:
        runner, model, effort = resolve_route(cfg, tiers[0], implementer)
        assembled = assemble(page_dir, target, text, 1, cfg=cfg, runner=runner)
    except ValueError as exc:
        raise errors.not_found(str(exc)) from exc
    estimate = summary.run_input(assembled.estimate()) or {}
    return models.InputPreview.model_validate(
        {
            "kind": kind,
            "tier": 1,
            "runner": runner,
            "model": model,
            "effort": effort,
            "parts": estimate["parts"],
            "total_est": estimate["total_est"],
        }
    )
