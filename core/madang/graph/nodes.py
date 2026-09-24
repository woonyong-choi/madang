"""흐름 그래프의 노드.

노드는 상태의 id로 페이지 파일을 찾아 읽고 쓴다. 분기하는 노드는 다음
노드를 ``Command``로 정한다. 모델은 직접 부르지 않으며 요청 종류는 결정기가
고른다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langgraph.graph import END
from langgraph.types import Command, RunnableConfig, interrupt

from madang.config import Config, Tier
from madang.deciders import Question, build_chain, target_kind
from madang.graph import events, steps
from madang.graph.state import FlowState
from madang.runners.base import CliRunner, RunEvent
from madang.runners.record import RecordedRun
from madang.store import pages, runs
from madang.store.page import STATE_FILE
from madang.validate import Issue

RunnerFactory = Callable[[str, Config], CliRunner]

OPPOSITE = "opposite"
PRIMARY = "primary"
DEFAULT_EFFORT = "medium"
REVIEW_KIND = "review"
# 답만 하면 끝나는 종류. 상태가 그대로여도 다시 실행하지 않는다.
ANSWER_KINDS = ("explore",)
# validate가 보정하지 않고 judge가 review로 강등해 처리하는 문제.
JUDGED_ISSUES = ("done-without-verify",)

# 사람에게 묻는 이유와 답.
WAIT_KIND = "kind"
WAIT_BLOCKED = "blocked"
WAIT_RUN_LIMIT = "run_limit"
WAIT_REPAIR = "repair_failed"
WAIT_REVIEW = "review_failed"
RETRY = "retry"
STOP = "stop"

REVIEW_REQUEST = """\
이번 실행은 리뷰다. 구현하지 말고 검토만 한다.
1. state.md, 산출물, 바뀐 파일을 읽고 아래 요청과 목표를 만족하는지 본다.
2. 통과면 state.md의 status를 review로 그대로 둔다.
3. 고칠 것이 있으면 status를 doing으로 바꾸고 "다음 할 일"에 지적을 \
1~3개로 쓴다.

요청:
{request}"""

REPAIR_REQUEST = """\
state.md 검사에서 아래 문제가 나왔다. 다른 작업은 하지 말고 이 문제만 \
고친다.

{issues}"""


class FlowNodes:
    """흐름 그래프의 노드 함수와 그들이 함께 쓰는 의존성.

    Attributes:
        cfg: 앱 홈 설정.
        make_runner: 러너 이름으로 러너를 만든다.
        on_event: 이벤트를 받는 콜백.
        cancelled: 설정되면 다음 실행을 시작하지 않고 진행 중인 실행을
            멈춘다.
    """

    def __init__(
        self,
        cfg: Config,
        make_runner: RunnerFactory,
        on_event: events.EventHook,
        cancelled: threading.Event,
    ) -> None:
        self.cfg = cfg
        self.make_runner = make_runner
        self.on_event = on_event
        self.cancelled = cancelled
        self.chain = build_chain(cfg.routes)
        self._lock = threading.Lock()
        self._active: CliRunner | None = None

    # 노드

    def classify(self, state: FlowState, config: RunnableConfig) -> Command:
        """요청 종류를 정한다. 블록 대상이면 고정, 아니면 결정기에 묻는다."""
        kind = target_kind(state["target"])
        if kind is None:
            text = steps.message_text(self._page_dir(state), state["message"])
            kinds = list(self.cfg.routes.kinds)
            decision = self.chain.decide(Question("choice", text, kinds))
            if decision is None:
                return self._wait(state, config, WAIT_KIND, kinds)
            kind = str(decision.choice)
        return Command(goto="pick", update={"kind": kind})

    def pick(self, state: FlowState) -> dict[str, Any]:
        """``routes.tiers[kind][tier]``에서 러너, 모델, 추론 강도를 고른다."""
        page_dir = self._page_dir(state)
        runner, model, effort = self._resolve(
            self._tiers(state["kind"])[state["tier"] - 1],
            self._implementer(state, page_dir),
        )

        def mark(header: dict[str, Any]) -> None:
            header["tier"] = state["tier"]
            header["attempts"] = state["attempts"]
            if state["kind"] != REVIEW_KIND:
                header["owner"] = f"{runner}/{model}"

        pages.update_state(page_dir, mark)
        return {"runner": runner, "model": model, "effort": effort}

    def assemble(self, state: FlowState) -> dict[str, Any]:
        """메시지 본문으로 프롬프트를 조립해 저장한다."""
        page_dir = self._page_dir(state)
        request = steps.message_text(page_dir, state["message"])
        self._prepare(state, request, state["tier"])
        return {}

    def run(self, state: FlowState) -> Command:
        """저장된 프롬프트로 러너를 새 세션에서 실행한다."""
        if self.cancelled.is_set():
            return Command(goto=END, update={"result_status": "cancelled"})
        recorded = self._execute(state, state["kind"], state["tier"])
        return Command(goto="validate", update=_counted(state, recorded))

    def validate(self, state: FlowState, config: RunnableConfig) -> Command:
        """실행 뒤 페이지를 검사하고 실행을 커밋한다."""
        issues = self._check(state)
        if not _blocking(issues):
            return Command(goto="judge")
        return self._next(state, config, "repair")

    def repair(self, state: FlowState, config: RunnableConfig) -> Command:
        """검사 문제만 고치라는 짧은 요청을 같은 러너로 한 번 실행한다."""
        if self.cancelled.is_set():
            return Command(goto=END, update={"result_status": "cancelled"})
        page_dir = self._page_dir(state)
        found = steps.check(page_dir, self.cfg, state["run_n"])
        lines = "\n".join(f"- {issue.format()}" for issue in found)
        self._prepare(state, REPAIR_REQUEST.format(issues=lines), state["tier"])
        recorded = self._execute(state, state["kind"], state["tier"])
        update = _counted(state, recorded)
        if _blocking(self._check({**state, **update})):
            return self._wait(state, config, WAIT_REPAIR, update=update)
        return Command(goto="judge", update=update)

    def judge(self, state: FlowState, config: RunnableConfig) -> Command:
        """실행 결과로 끝, 리뷰, 재실행, 승격 중 하나를 고른다."""
        page_dir = self._page_dir(state)
        record = runs.read_run(page_dir, state["run_n"])
        status = record.result_status or "doing"
        if status == "cancelled":
            return Command(goto=END, update={"result_status": "cancelled"})
        if _reviewing(state):
            return self._judge_review(state, config, status)
        if status == "error":
            attempts = state["attempts"] + 1
            if attempts < self.cfg.routes.limits.blocked_after_failures:
                update = {"attempts": attempts, "result_status": "doing"}
                return self._next(state, config, "pick", update)
            status = "blocked"
        if status == "blocked":
            return self._promote(state, config)
        if status == "done" and record.verify.ok:
            return Command(goto="commit", update={"result_status": "done"})
        if status in ("done", "review"):
            if status == "done":
                _set_status(page_dir, "review")
            update = {"result_status": "review"}
            return self._next(state, config, "review_run", update)
        if state["kind"] in ANSWER_KINDS:
            return Command(goto=END, update={"result_status": status})
        update = {"result_status": "doing"}
        return self._next(state, config, "pick", update)

    def review_run(self, state: FlowState) -> Command:
        """구현한 쪽의 반대편 러너로 review 종류를 실행한다."""
        if self.cancelled.is_set():
            return Command(goto=END, update={"result_status": "cancelled"})
        page_dir = self._page_dir(state)
        entries = self._tiers(REVIEW_KIND, required=False)
        entry = entries[0] if entries else Tier(runner=OPPOSITE, model=PRIMARY)
        runner, model, effort = self._resolve(
            entry, self._implementer(state, page_dir)
        )
        reviewer: FlowState = {
            **state,
            "runner": runner,
            "model": model,
            "effort": effort,
        }
        request = steps.message_text(page_dir, state["message"])
        self._prepare(reviewer, REVIEW_REQUEST.format(request=request), 1)
        recorded = self._execute(reviewer, REVIEW_KIND, 1)
        update = {
            "runner": runner,
            "model": model,
            "effort": effort,
            **_counted(state, recorded),
        }
        return Command(goto="validate", update=update)

    def commit(self, state: FlowState) -> dict[str, Any]:
        """페이지를 done으로 표시하고 남은 변경을 앱 홈에 커밋한다.

        리뷰를 통과한 실행은 그 리뷰가 검증이므로 ``verify.ok``를 참으로
        남긴다.
        """
        page_dir = self._page_dir(state)
        record = runs.read_run(page_dir, state["run_n"])
        changed = []
        if not record.verify.ok:
            record.verify.ok = True
            runs.write_run(page_dir, record)
            changed.append(runs.record_path(page_dir, record.n))
        if steps.state_status(page_dir) != "done":
            _set_status(page_dir, "done")
            changed.append(page_dir / STATE_FILE)
        if changed:
            files = [p.relative_to(page_dir).as_posix() for p in changed]
            steps.commit_run(page_dir, self.cfg.home, record, sorted(files))
        return {"result_status": "done"}

    def ask_human(self, state: FlowState) -> Command:
        """흐름을 멈추고 사람의 답을 기다린다. 답에 따라 이어 간다."""
        decision = state["pending_decision"] or {}
        choice = interrupt(decision)
        cleared: dict[str, Any] = {"pending_decision": None}
        if decision.get("reason") == WAIT_KIND:
            return Command(goto="pick", update={**cleared, "kind": choice})
        if choice == STOP:
            return Command(goto=END, update=cleared)
        update = {**cleared, "attempts": 0, "runs_this_message": 0}
        return Command(goto=decision["retry"], update=update)

    def cancel(self) -> None:
        """진행 중인 실행을 멈추고 이후 실행을 막는다."""
        self.cancelled.set()
        with self._lock:
            active = self._active
        if active is not None:
            active.cancel()

    # 분기

    def _judge_review(
        self, state: FlowState, config: RunnableConfig, status: str
    ) -> Command:
        if status == "error":
            again = "pick" if state["kind"] == REVIEW_KIND else "review_run"
            return self._wait(state, config, WAIT_REVIEW, retry=again)
        if status in ("review", "done"):
            return Command(goto="commit", update={"result_status": "done"})
        _set_status(self._page_dir(state), "doing")
        update = {"result_status": "doing"}
        if state["kind"] == REVIEW_KIND:
            return Command(goto=END, update=update)
        return self._next(state, config, "pick", update)

    def _promote(self, state: FlowState, config: RunnableConfig) -> Command:
        update: dict[str, Any] = {"result_status": "blocked", "attempts": 0}
        if state["tier"] < len(self._tiers(state["kind"])):
            update["tier"] = state["tier"] + 1
            return self._next(state, config, "pick", update)
        return self._wait(state, config, WAIT_BLOCKED, update=update)

    def _next(
        self,
        state: FlowState,
        config: RunnableConfig,
        node: str,
        update: dict[str, Any] | None = None,
    ) -> Command:
        """실행 한도 안이면 ``node``로, 넘으면 사람에게 간다."""
        limit = self.cfg.routes.limits.max_runs_per_message
        if state["runs_this_message"] >= limit:
            return self._wait(
                state, config, WAIT_RUN_LIMIT, retry=node, update=update
            )
        return Command(goto=node, update=update or {})

    def _wait(
        self,
        state: FlowState,
        config: RunnableConfig,
        reason: str,
        options: list[str] | None = None,
        *,
        retry: str = "pick",
        update: dict[str, Any] | None = None,
    ) -> Command:
        """``flow.waiting``을 알리고 ask_human으로 간다."""
        decision = {
            "reason": reason,
            "options": options or [RETRY, STOP],
            "retry": retry,
        }
        payload = {
            **_base(state),
            "thread_id": config["configurable"]["thread_id"],
            "decision": decision,
        }
        self.on_event(events.FLOW_WAITING, payload)
        return Command(
            goto="ask_human",
            update={**(update or {}), "pending_decision": decision},
        )

    # 단계

    def _prepare(self, state: FlowState, request: str, tier: int) -> None:
        assembled = steps.prepare(
            self._page_dir(state),
            cfg=self.cfg,
            runner=state["runner"],
            message=state["message"],
            target=state["target"].get("block"),
            request=request,
            tier=tier,
        )
        payload = {**_base(state), "input": assembled.estimate()}
        self.on_event(events.RUN_ASSEMBLED, payload)

    def _execute(self, state: FlowState, kind: str, tier: int) -> RecordedRun:
        page_dir = self._page_dir(state)
        runner = self.make_runner(state["runner"], self.cfg)
        route = {
            "model": state["model"],
            "effort": state["effort"],
            "kind": kind,
            "tier": tier,
        }
        self.on_event(
            events.RUN_STARTED,
            {**_base(state), "runner": runner.name, **route},
        )
        with self._lock:
            self._active = runner
        try:
            recorded = steps.execute(
                page_dir,
                runner,
                cfg=self.cfg,
                message=state["message"],
                route=route,
                trigger=_trigger(state),
                on_event=self._progress(state, page_dir, runner),
            )
        finally:
            with self._lock:
                self._active = None
        steps.reply(page_dir, recorded)
        self._announce(state, recorded)
        return recorded

    def _progress(
        self, state: FlowState, page_dir: Path, runner: CliRunner
    ) -> Callable[[RunEvent], None]:
        def relay(event: RunEvent) -> None:
            # 실행 직전에 온 취소는 러너가 잊으므로 여기서 다시 멈춘다.
            if self.cancelled.is_set():
                runner.cancel()
            payload = {
                **_base(state),
                "n": runs.current(page_dir),
                "event": event.to_dict(),
            }
            self.on_event(events.RUN_PROGRESS, payload)

        return relay

    def _announce(self, state: FlowState, recorded: RecordedRun) -> None:
        result = recorded.result
        name = (
            events.RUN_FINISHED
            if result.status == "done"
            else (events.RUN_FAILED)
        )
        payload = {
            **_base(state),
            "n": recorded.n,
            "status": result.status,
            "usage": recorded.record.usage.model_dump(),
            "error": result.error,
        }
        self.on_event(name, payload)

    def _check(self, state: FlowState) -> list[Issue]:
        """실행을 검사하고, 미등록 파일을 알리고, 커밋한다."""
        page_dir = self._page_dir(state)
        issues = steps.check(page_dir, self.cfg, state["run_n"])
        record = runs.read_run(page_dir, state["run_n"])
        if record.unknown_files:
            payload = {
                **_base(state),
                "n": record.n,
                "files": record.unknown_files,
            }
            self.on_event(events.PAGE_UNKNOWN_FILES, payload)
        steps.commit_run(page_dir, self.cfg.home, record)
        return issues

    # 라우팅 표

    def _page_dir(self, state: FlowState) -> Path:
        return (
            self.cfg.home
            / pages.SPACES_DIR
            / state["space"]
            / pages.PAGES_DIR
            / state["page"]
        )

    def _tiers(self, kind: str, *, required: bool = True) -> list[Tier]:
        tiers = self.cfg.routes.tiers.get(kind) or []
        if required and not tiers:
            raise ValueError(f"routes.yaml has no tiers for kind '{kind}'")
        return tiers

    def _implementer(self, state: FlowState, page_dir: Path) -> str:
        """마지막으로 구현한 러너.

        pick이 구현 실행마다 state.md의 owner를 남기므로 그것을 먼저 본다.
        흐름 상태의 러너는 리뷰 뒤라면 리뷰한 쪽일 수 있다.
        """
        owner = pages.read_header(page_dir / STATE_FILE).get("owner")
        return str(owner).split("/", 1)[0] if owner else state["runner"]

    def _resolve(self, entry: Tier, implementer: str) -> tuple[str, str, str]:
        """``opposite``와 ``primary``를 실제 러너와 모델로 바꾼다."""
        runner = entry.runner
        if runner == OPPOSITE:
            others = [name for name in self.cfg.runners if name != implementer]
            runner = others[0] if others else implementer
        model, effort = entry.model, entry.effort
        if model == PRIMARY:
            model, primary_effort = self._primary(runner)
            effort = effort or primary_effort
        return runner, model, effort or DEFAULT_EFFORT

    def _primary(self, runner: str) -> tuple[str, str | None]:
        """라우팅 표에서 ``runner``가 처음 맡는 모델과 추론 강도."""
        for tiers in self.cfg.routes.tiers.values():
            for tier in tiers:
                if tier.runner == runner and tier.model != PRIMARY:
                    return tier.model, tier.effort
        raise ValueError(f"routes.yaml has no model for runner '{runner}'")


def _base(state: FlowState) -> dict[str, Any]:
    return {"page": state["page"], "message": state["message"]}


def _trigger(state: FlowState) -> dict[str, Any]:
    target = state["target"]
    trigger: dict[str, Any] = {
        "message": state["message"],
        "target": target.get("block") or "page",
    }
    if target.get("elements"):
        trigger["elements"] = list(target["elements"])
    if target.get("mode"):
        trigger["mode"] = target["mode"]
    return trigger


def _counted(state: FlowState, recorded: RecordedRun) -> dict[str, Any]:
    return {
        "run_n": recorded.n,
        "runs_this_message": state["runs_this_message"] + 1,
    }


def _reviewing(state: FlowState) -> bool:
    """방금 끝난 실행이 리뷰인지 여부."""
    return REVIEW_KIND in (state["result_status"], state["kind"])


def _blocking(issues: list[Issue]) -> bool:
    return any(issue.code not in JUDGED_ISSUES for issue in issues)


def _set_status(page_dir: Path, status: str) -> None:
    pages.update_state(page_dir, lambda header: header.update(status=status))
