"""러너 가용성과 대체: 대체표, 조기 실패 재실행, 리뷰 보류, no_runner."""

import json
from pathlib import Path

import pytest
import yaml
from api_support import PROJECT, WS, Script, set_status
from fastapi.testclient import TestClient

from madang.api.app import create_app
from madang.config import load_config
from madang.graph import Flow
from madang.runners.availability import (
    NOT_INSTALLED,
    NOT_LOGGED_IN,
    Availability,
)
from madang.runners.base import RunResult, Usage
from madang.runners.fallback import Fallbacks, Route
from madang.store import frontmatter, pages, projects

LOCAL = "http://127.0.0.1"


class Doors:
    """러너별로 쓸 수 없는 이유를 정하는 가짜 확인. 확인 횟수를 센다."""

    def __init__(self, **closed: str) -> None:
        self.closed = dict(closed)
        self.probes = 0

    def probe(self, name: str, spec) -> str | None:
        self.probes += 1
        return self.closed.get(name)


def early_error(message: str, seconds: float = 3.0):
    """시작 직후 ``message``로 실패하는 에이전트 동작."""

    def act(page_dir: Path) -> RunResult:
        return RunResult(status="error", error=message, duration=seconds)

    return act


class FlowScript(Script):
    """동작이 RunResult를 주면 그대로 돌려주는 대본."""

    def runner(self, name: str, cfg):
        return FlowRunner(name, self)


class FlowRunner:
    def __init__(self, name: str, script: FlowScript) -> None:
        self.name = name
        self.script = script

    def exec(self, **kw) -> RunResult:
        page_dir = kw["events_log"].parent.parent
        self.script.calls.append({**kw, "name": self.name})
        outcome = self.script.acts.pop(0)(page_dir)
        if isinstance(outcome, RunResult):
            return outcome
        return RunResult(
            status=outcome or "done",
            usage=Usage(input=10, cached=1, output=2),
            final_text="ANSWER",
            duration=0.1,
        )

    def cancel(self) -> None:
        pass


@pytest.fixture
def page(home: Path) -> Path:
    """앱 홈 픽스처(api_support)의 프로젝트에 만든 페이지 폴더."""
    pages_dir = projects.get(home, PROJECT).pages_dir
    return pages.create_page(pages_dir, "로그인", slug="login")


def flow(
    home: Path,
    script: FlowScript,
    doors: Doors,
    seen: list,
    availability: Availability | None = None,
) -> Flow:
    return Flow(
        load_config(home),
        runners=script.runner,
        on_event=lambda name, payload: seen.append((name, payload)),
        availability=availability or Availability(doors.probe),
    )


def record(page: Path, n: int) -> dict:
    return json.loads((page / f"runs/{n}.json").read_text())


def ledger(page: Path) -> dict:
    return pages.read_header(page / "ledger.md")


def calls(script: Script) -> list[tuple[str, str]]:
    return [(c["name"], c["model"]) for c in script.calls]


def named(seen: list, name: str) -> list[dict]:
    return [payload for kind, payload in seen if kind == name]


# 설정


def test_default_config_has_the_fallback_table(home: Path) -> None:
    rules = Fallbacks.from_routes(load_config(home).routes)
    assert rules.table["codex/gpt-6-sol"] == "claude/claude-opus-5-5"
    assert rules.table["claude/claude-haiku-4-5"] == "codex/gpt-6-luna"
    assert rules.early_failure.within_seconds == 90
    assert "not logged in" in rules.early_failure.patterns
    other = rules.replacement(Route("codex", "gpt-6-luna", "high"))
    assert other == Route("claude", "claude-sonnet-5", "high")
    assert rules.replacement(Route("codex", "unknown", "high")) is None


def test_missing_keys_use_bundled_defaults(home: Path) -> None:
    path = home / "config.yaml"
    data = yaml.safe_load(path.read_text())
    del data["routes"]["fallbacks"]
    data["routes"]["early_failure"] = {"within_seconds": 5, "patterns": ["x"]}
    path.write_text(yaml.safe_dump(data, allow_unicode=True))

    rules = Fallbacks.from_routes(load_config(home).routes)
    assert rules.table["codex/gpt-6-sol"] == "claude/claude-opus-5-5"
    assert rules.early_failure.within_seconds == 5
    assert rules.early_failure.patterns == ["x"]


def test_malformed_fallback_entry_is_rejected(home: Path) -> None:
    path = home / "config.yaml"
    data = yaml.safe_load(path.read_text())
    data["routes"]["fallbacks"] = {"codex": "claude/claude-opus-5-5"}
    path.write_text(yaml.safe_dump(data, allow_unicode=True))

    with pytest.raises(ValueError, match="runner/model"):
        Fallbacks.from_routes(load_config(home).routes)


def test_early_failure_needs_error_time_and_pattern(home: Path) -> None:
    rules = Fallbacks.from_routes(load_config(home).routes)

    def result(status="error", error="Error: Not logged in", duration=2.0):
        return RunResult(status=status, error=error, duration=duration)

    assert rules.early_failure_reason(result()) == "not logged in"
    assert rules.early_failure_reason(result(duration=91.0)) is None
    assert rules.early_failure_reason(result(error="tests failed")) is None
    assert rules.early_failure_reason(result(status="blocked")) is None


def test_availability_reason_uses_the_cache(home: Path) -> None:
    doors = Doors(codex=NOT_LOGGED_IN)
    availability = Availability(doors.probe)
    runners = load_config(home).runners

    assert availability.reason("codex", runners) == NOT_LOGGED_IN
    assert availability.reason("claude", runners) is None
    assert availability.reason("other", runners) is None
    assert doors.probes == 2


# 흐름


def test_unavailable_runner_falls_back_in_pick(home: Path, page: Path) -> None:
    script = FlowScript(set_status("review"), set_status("review"))
    seen: list = []
    doors = Doors(codex=NOT_LOGGED_IN)
    result = flow(home, script, doors, seen).start(page.name, "구현해줘")

    assert result.waiting is None
    assert result.state["result_status"] == "done"
    # build 1단계(codex/gpt-6-sol)를 대체표대로 claude/claude-opus-5-5로
    build, review = calls(script)
    assert build == ("claude", "claude-opus-5-5")
    assert script.calls[0]["effort"] == "medium"
    assert record(page, 1)["tier"] == 1
    assert record(page, 1)["fallback"] == {
        "from": "codex/gpt-6-sol",
        "to": "claude/claude-opus-5-5",
        "reason": "unavailable",
    }
    assert ledger(page)["owner"] == "claude/claude-opus-5-5"
    fallbacks = named(seen, "run.fallback")
    assert fallbacks[0]["from"] == "codex/gpt-6-sol"
    assert fallbacks[0]["reason"] == "unavailable"


def test_review_without_opposite_is_pending(home: Path, page: Path) -> None:
    script = FlowScript(set_status("review"), set_status("review"))
    seen: list = []
    doors = Doors(codex=NOT_INSTALLED)
    result = flow(home, script, doors, seen).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    build, review = calls(script)
    # 반대편(codex)이 없으니 같은 도구(claude)의 다른 모델로 리뷰한다
    assert review[0] == "claude" and review[1] != build[1]
    assert record(page, 2)["kind"] == "review"
    assert record(page, 2)["fallback"]["from"] == "codex/gpt-6-sol"
    assert record(page, 2)["fallback"]["to"] == f"claude/{review[1]}"
    header = ledger(page)
    assert header["cross_review"] == "pending"
    assert header["status"] == "done"
    assert header["owner"] == "claude/claude-opus-5-5"
    assert len(named(seen, "run.fallback")) == 2


def test_cross_review_clears_pending(home: Path, page: Path) -> None:
    pages.update_state(
        page,
        lambda h: h.update(
            owner="claude/claude-opus-5-5", cross_review="pending"
        ),
    )
    script = FlowScript(set_status("review"))
    seen: list = []
    result = flow(home, script, Doors(), seen).start(page.name, "review: 봐줘")

    assert result.state["kind"] == "review"
    assert calls(script)[0][0] == "codex"
    assert "cross_review" not in ledger(page)
    assert "fallback" not in record(page, 1)
    assert not named(seen, "run.fallback")


def test_early_failure_retries_once_with_fallback(
    home: Path, page: Path
) -> None:
    script = FlowScript(
        early_error("ERROR: model not found: gpt-6-sol"),
        set_status("review"),
        set_status("review"),
    )
    seen: list = []
    result = flow(home, script, Doors(), seen).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    assert calls(script)[:2] == [
        ("codex", "gpt-6-sol"),
        ("claude", "claude-opus-5-5"),
    ]
    first, retried = record(page, 1), record(page, 2)
    assert first["result_status"] == "error" and "fallback" not in first
    assert retried["fallback"] == {
        "from": "codex/gpt-6-sol",
        "to": "claude/claude-opus-5-5",
        "reason": "model not found",
    }
    # 다시 실행해도 승격하지 않는다
    assert retried["tier"] == 1
    assert ledger(page)["tier"] == 1 and ledger(page)["attempts"] == 0
    assert ledger(page)["owner"] == "claude/claude-opus-5-5"
    # 리뷰는 실제 구현한 쪽(claude)의 반대편
    assert calls(script)[2] == ("codex", "gpt-6-sol")
    assert result.state["runs_this_message"] == 3
    assert [p["reason"] for p in named(seen, "run.fallback")] == [
        "model not found"
    ]


def test_late_or_unmatched_failure_is_not_retried(
    home: Path, page: Path
) -> None:
    script = FlowScript(
        early_error("not logged in", seconds=120.0),
        early_error("segfault"),
        set_status("review"),
        set_status("review"),
    )
    seen: list = []
    result = flow(home, script, Doors(), seen).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    # 늦은 실패와 패턴 없는 실패는 판정(재시도·승격)에 맡긴다
    assert calls(script)[:3] == [
        ("codex", "gpt-6-sol"),
        ("codex", "gpt-6-sol"),
        ("claude", "claude-opus-5-5"),
    ]
    assert record(page, 3)["tier"] == 2
    assert not named(seen, "run.fallback")


def test_no_runner_waits_and_resumes(home: Path, page: Path) -> None:
    doors = Doors(codex=NOT_LOGGED_IN, claude=NOT_LOGGED_IN)
    script = FlowScript(set_status("review"), set_status("review"))
    seen: list = []
    result = flow(home, script, doors, seen).start(page.name, "구현해줘")

    assert result.waiting == {
        "reason": "no_runner",
        "options": ["retry", "stop"],
        "retry": "pick",
    }
    assert script.calls == []
    assert named(seen, "flow.waiting")[0]["decision"]["reason"] == "no_runner"

    # 사람이 로그인한 뒤 다시 하라고 답하면 캐시를 버리고 다시 확인한다
    doors.closed = {"codex": NOT_LOGGED_IN}
    resumed = flow(home, script, doors, seen).resume(result.thread_id, "retry")
    assert resumed.waiting is None
    assert resumed.state["result_status"] == "done"
    assert calls(script)[0] == ("claude", "claude-opus-5-5")


def test_review_waits_when_no_runner_is_left(home: Path, page: Path) -> None:
    doors = Doors(codex=NOT_LOGGED_IN)
    script = FlowScript(set_status("review"), set_status("review"))
    seen: list = []
    availability = Availability(doors.probe)

    def close_claude(page_dir: Path) -> None:
        set_status("review")(page_dir)
        doors.closed["claude"] = NOT_LOGGED_IN
        availability.get(load_config(home).runners, fresh=True)

    script.acts = [close_claude, set_status("review")]
    runner = flow(home, script, doors, seen, availability)
    result = runner.start(page.name, "구현해줘")

    assert result.waiting is not None
    assert result.waiting["reason"] == "no_runner"
    assert result.waiting["retry"] == "review_run"
    assert len(script.calls) == 1


# API


def test_api_relays_fallback_event(
    home: Path, contract, tmp_path: Path
) -> None:
    script = Script(set_status("review"), set_status("review"))
    app = create_app(
        home,
        runners=script.runner,
        probe=Doors(codex=NOT_LOGGED_IN).probe,
        claude_dir=tmp_path / "no-claude",
        codex_dir=tmp_path / "no-codex",
    )
    with TestClient(app, base_url=LOCAL) as client:
        page_id = client.post(
            f"/projects/{PROJECT}/pages", json={"title": "로그인"}
        ).json()["id"]
        received: list[dict] = []
        with client.websocket_connect(f"{WS}/events") as ws:
            client.post(f"/pages/{page_id}/messages", json={"text": "구현해줘"})
            while True:
                event = ws.receive_json()
                received.append(event)
                if (
                    event["type"] == "page.updated"
                    and event["data"]["page"]["status"] == "done"
                ):
                    break
        client.app.state.core.flows.join(page_id, 20.0)

        for event in received:
            contract.event(event)
        fallback = next(e for e in received if e["type"] == "run.fallback")
        assert fallback["run"] == 1
        assert fallback["data"] == {
            "from": "codex/gpt-6-sol",
            "to": "claude/claude-opus-5-5",
            "reason": "unavailable",
        }
        started = next(e for e in received if e["type"] == "run.started")
        assert started["data"]["runner"] == "claude"
        run = contract.check(client.get(f"/pages/{page_id}/runs/1"), 200)
        assert run["fallback"]["to"] == "claude/claude-opus-5-5"
        runners = contract.check(client.get("/runners"), 200)
        codex = next(r for r in runners["runners"] if r["name"] == "codex")
        assert codex == {
            "name": "codex",
            "available": False,
            "auth": "subscription",
            "reason": NOT_LOGGED_IN,
        }


def test_no_runner_is_reported_by_the_api(
    home: Path, contract, tmp_path: Path
) -> None:
    script = Script()
    closed = Doors(codex=NOT_LOGGED_IN, claude=NOT_INSTALLED)
    app = create_app(
        home,
        runners=script.runner,
        probe=closed.probe,
        claude_dir=tmp_path / "no-claude",
        codex_dir=tmp_path / "no-codex",
    )
    with TestClient(app, base_url=LOCAL) as client:
        page_id = client.post(
            f"/projects/{PROJECT}/pages", json={"title": "로그인"}
        ).json()["id"]
        client.post(f"/pages/{page_id}/messages", json={"text": "구현해줘"})
        client.app.state.core.flows.join(page_id, 20.0)
        detail = contract.check(client.get(f"/pages/{page_id}"), 200)

    assert detail["waiting"]["reason"] == "no_runner"
    assert detail["waiting"]["decision"]["question"]["options"] == [
        "retry",
        "stop",
    ]
    assert "로그인" in detail["waiting"]["decision"]["question"]["prompt"]
    assert script.calls == []


def test_ledger_with_pending_cross_review_stays_valid(page: Path) -> None:
    from madang.validate import validate_target

    header, body = frontmatter.read(page / "ledger.md")
    header["cross_review"] = "pending"
    (page / "ledger.md").write_text(frontmatter.dumps(header, body))
    assert validate_target(page) == []


def test_early_failed_review_on_same_tool_is_pending(
    home: Path, page: Path
) -> None:
    script = FlowScript(
        set_status("review"),
        early_error("You've hit your usage limit."),
        set_status("review"),
    )
    seen: list = []
    result = flow(home, script, Doors(), seen).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    assert calls(script) == [
        ("codex", "gpt-6-sol"),
        ("claude", "claude-opus-5-5"),
        ("codex", "gpt-6-sol"),
    ]
    assert record(page, 3)["fallback"]["reason"] == "usage limit"
    assert record(page, 3)["kind"] == "review"
    assert ledger(page)["cross_review"] == "pending"
    assert ledger(page)["owner"] == "codex/gpt-6-sol"
