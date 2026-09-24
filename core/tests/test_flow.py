import json
import threading
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from madang import cli
from madang.config import load_config
from madang.graph import Flow, build_graph, resume
from madang.graph.nodes import FlowNodes
from madang.runners.base import RunEvent, RunResult, Usage
from madang.store import frontmatter, pages, projects
from madang.store.home import init_home


def set_status(status: str, todo: str | None = None):
    """ledger.md의 status(와 다음 할 일)를 바꾸는 에이전트 동작."""

    def act(page_dir: Path) -> None:
        state = page_dir / "ledger.md"
        header, body = frontmatter.read(state)
        header["status"] = status
        if todo is not None:
            body = body.replace("## 다음 할 일\n", f"## 다음 할 일\n{todo}\n")
        state.write_text(frontmatter.dumps(header, body))

    return act


def break_state(page_dir: Path) -> None:
    (page_dir / "ledger.md").write_text("---\nstatus: nope\n---\n")


def restore_state(status: str):
    def act(page_dir: Path) -> None:
        header = {"status": status, "kind": "build", "tier": 1, "attempts": 0}
        body = "## 목표\n이력서\n\n## 다음 할 일\n1. 없음\n"
        (page_dir / "ledger.md").write_text(frontmatter.dumps(header, body))

    return act


def runner_error(page_dir: Path) -> str:
    return "error"


class Script:
    """러너 호출 순서대로 에이전트 동작을 내준다. 모든 호출을 기록한다."""

    def __init__(self, *acts):
        self.acts = list(acts)
        self.calls: list[dict] = []

    def runner(self, name: str, cfg) -> "FakeRunner":
        return FakeRunner(name, self)


class FakeRunner:
    def __init__(self, name: str, script: Script):
        self.name = name
        self.script = script
        self.cancelled = False

    def exec(self, **kw) -> RunResult:
        page_dir = kw["events_log"].parent.parent
        kw["name"] = self.name
        self.script.calls.append(kw)
        act = self.script.acts.pop(0)
        status = act(page_dir) or "done"
        kw["on_event"](RunEvent("text", text="working"))
        return RunResult(
            status=status,
            usage=Usage(input=100, cached=10, output=5),
            final_text=f"ANSWER-{len(self.script.calls)}",
            duration=0.1,
            error=None if status == "done" else "boom",
        )

    def cancel(self) -> None:
        self.cancelled = True


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("MADANG_BY", raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    init_home(root)
    (tmp_path / "work").mkdir()
    projects.add(root, tmp_path / "work")
    return root


@pytest.fixture
def page(home: Path) -> Path:
    pages_dir = projects.get(home, "work").pages_dir
    return pages.create_page(pages_dir, "이력서", slug="resume")


def flow(home: Path, script: Script, seen: list | None = None) -> Flow:
    def on_event(name, payload):
        if seen is not None:
            seen.append((name, payload))

    return Flow(load_config(home), runners=script.runner, on_event=on_event)


def record(page: Path, n: int) -> dict:
    return json.loads((page / f"runs/{n}.json").read_text())


def header(page: Path) -> dict:
    return pages.read_header(page / "ledger.md")


def routes_limit(home: Path, **limits) -> None:
    path = home / "config.yaml"
    data = yaml.safe_load(path.read_text())
    data["routes"]["limits"].update(limits)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


def test_graph_has_every_node(home: Path) -> None:
    nodes = FlowNodes(
        load_config(home), Script().runner, print, threading.Event()
    )
    names = set(build_graph(nodes).nodes)
    assert names == {
        "classify",
        "pick",
        "assemble",
        "run",
        "validate",
        "repair",
        "judge",
        "review_run",
        "settle",
        "finish",
        "ask_human",
    }


def test_done_after_opposite_review(home: Path, page: Path) -> None:
    script = Script(set_status("review"), set_status("review"))
    seen: list = []
    result = flow(home, script, seen).start(page.name, "로그인 화면 만들어줘")

    assert result.waiting is None
    assert result.state["result_status"] == "done"
    assert result.state["runs_this_message"] == 2
    build, review = script.calls
    assert (build["name"], build["model"]) == ("codex", "gpt-6-sol")
    assert build["effort"] == "medium"
    assert review["name"] == "claude" and review["model"] == "claude-opus-5-5"
    assert "로그인 화면 만들어줘" in review["prompt"]
    assert "리뷰" in review["prompt"]

    assert record(page, 1)["kind"] == "build"
    assert record(page, 2)["kind"] == "review"
    assert record(page, 2)["verify"]["ok"] is True
    state = header(page)
    assert state["status"] == "done" and state["owner"] == "codex/gpt-6-sol"
    assert not (home / ".git").exists()

    names = [name for name, _ in seen]
    for name in ("run.assembled", "run.started", "run.progress"):
        assert name in names
    assert names.count("run.finished") == 2
    progress = next(p for n, p in seen if n == "run.progress")
    assert progress["n"] == 1 and progress["event"]["type"] == "text"
    assert "flow.waiting" not in names


def test_blocked_promotes_then_done(home: Path, page: Path) -> None:
    (page / "ledger.md").write_text(
        (page / "ledger.md").read_text() + "LOG-LINE\n"
    )
    script = Script(
        set_status("blocked"), set_status("review"), set_status("review")
    )
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    first, promoted, review = script.calls
    assert first["name"] == "codex"
    assert (promoted["name"], promoted["model"]) == (
        "claude",
        "claude-opus-5-5",
    )
    assert "LOG-LINE" in first["prompt"]
    assert "LOG-LINE" not in promoted["prompt"]
    assert record(page, 2)["tier"] == 2
    # 구현한 쪽(claude)의 반대편이 리뷰한다
    assert (review["name"], review["model"]) == ("codex", "gpt-6-sol")
    assert header(page)["tier"] == 2


def test_review_fail_goes_back_to_pick(home: Path, page: Path) -> None:
    script = Script(
        set_status("review"),
        set_status("doing", "- 테스트를 추가한다"),
        set_status("review"),
        set_status("review"),
    )
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    assert [c["name"] for c in script.calls] == [
        "codex",
        "claude",
        "codex",
        "claude",
    ]
    assert "테스트를 추가한다" in script.calls[2]["prompt"]
    assert record(page, 3)["tier"] == 1
    assert header(page)["status"] == "done"


def test_review_message_uses_opposite_of_owner(home: Path, page: Path) -> None:
    pages.update_state(page, lambda h: h.update(owner="claude/x"))
    script = Script(set_status("doing", "- 이름을 고친다"))
    result = flow(home, script).start(page.name, "review: 봐줘")

    assert result.state["kind"] == "review"
    assert result.state["result_status"] == "doing"
    assert script.calls[0]["name"] == "codex"
    assert header(page)["status"] == "doing"


def test_limit_waits_and_resumes(home: Path, page: Path) -> None:
    routes_limit(home, max_runs_per_message=2)
    script = Script(
        set_status("blocked"),
        set_status("blocked"),
        set_status("review"),
        set_status("review"),
    )
    seen: list = []
    result = flow(home, script, seen).start(page.name, "구현해줘")

    assert result.waiting == {
        "reason": "run_limit",
        "options": ["retry", "stop"],
        "retry": "pick",
    }
    assert result.state["tier"] == 3 and len(script.calls) == 2
    waiting = [p for n, p in seen if n == "flow.waiting"]
    assert waiting[0]["thread_id"] == result.thread_id

    with pytest.raises(ValueError, match="not one of"):
        flow(home, script).resume(result.thread_id, "maybe")

    # 새 core 프로세스처럼 core.db에서 이어 간다
    done = resume(
        result.thread_id, "retry", cfg=load_config(home), runners=script.runner
    )
    assert done.waiting is None and done.state["result_status"] == "done"
    assert script.calls[2]["model"] == "claude-fable-5-1"
    assert len(script.calls) == 4
    with pytest.raises(ValueError, match="not waiting"):
        flow(home, script).resume(result.thread_id, "retry")


def test_last_tier_blocked_waits_and_stops(home: Path, page: Path) -> None:
    script = Script(set_status("blocked"), set_status("blocked"))
    result = flow(home, script).start(page.name, "오타 고쳐줘")

    assert result.state["kind"] == "small"
    assert result.waiting["reason"] == "blocked"
    stopped = flow(home, script).resume(result.thread_id, "stop")
    assert stopped.waiting is None
    assert stopped.state["result_status"] == "blocked"
    assert len(script.calls) == 2


def test_runner_errors_count_as_failures(home: Path, page: Path) -> None:
    script = Script(
        runner_error,
        runner_error,
        set_status("review"),
        set_status("review"),
    )
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    assert [record(page, n)["tier"] for n in (1, 2, 3)] == [1, 1, 2]


def test_ambiguous_kind_asks_human(home: Path, page: Path) -> None:
    script = Script(set_status("review"), set_status("review"))
    result = flow(home, script).start(page.name, "구조를 검토해줘")

    assert result.waiting["reason"] == "kind"
    assert "design" in result.waiting["options"]
    assert script.calls == []
    done = flow(home, script).resume(result.thread_id, "design")
    assert done.state["kind"] == "design"
    assert script.calls[0]["model"] == "claude-opus-5-5"


def test_block_target_fixes_kind(home: Path, page: Path) -> None:
    (page / "blocks/b02-cv.md").write_text("CV-BODY\n")
    script = Script(set_status("review"), set_status("review"))
    target = {"block": "b02", "elements": ["work[1]"]}
    result = flow(home, script).start(page.name, "설계 다듬어줘", target)

    assert result.state["kind"] == "small"
    assert "CV-BODY" in script.calls[0]["prompt"]
    assert record(page, 1)["trigger"] == {
        "message": "b03",
        "target": "b02",
        "elements": ["work[1]"],
        "mode": "edit",
    }
    with pytest.raises(ValueError, match="b09"):
        flow(home, script).start(page.name, "x", {"block": "b09"})


def test_repair_fixes_invalid_state(home: Path, page: Path) -> None:
    script = Script(
        break_state,
        restore_state("review"),
        set_status("review"),
    )
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    repair = script.calls[1]
    assert repair["name"] == "codex"
    assert "ledger.md 검사" in repair["prompt"]
    assert record(page, 1)["state_check"]["ok"] is False
    assert record(page, 2)["state_check"]["ok"] is True


def test_failed_repair_asks_human(home: Path, page: Path) -> None:
    script = Script(break_state, break_state)
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.waiting["reason"] == "repair_failed"
    assert result.state["runs_this_message"] == 2


def test_done_without_verify_is_demoted(home: Path, page: Path) -> None:
    script = Script(set_status("done"), set_status("review"))
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.state["result_status"] == "done"
    assert len(script.calls) == 2
    assert script.calls[1]["name"] == "claude"


def test_explore_ends_after_answer(home: Path, page: Path) -> None:
    script = Script(lambda page_dir: None)
    result = flow(home, script).start(page.name, "이 함수 어디 있어?")

    assert result.state["kind"] == "explore"
    assert result.state["result_status"] == "planning"
    assert len(script.calls) == 1


def test_chat_page_defaults_to_its_work_kind(home: Path) -> None:
    pages_dir = projects.get(home, "work").pages_dir
    chat = pages.create_page(pages_dir, "잡담", slug="chat", kind="chat")
    script = Script(lambda page_dir: None)
    result = flow(home, script).start(chat.name, "오늘 할 만한 것")

    assert result.state["kind"] == "explore"
    assert len(script.calls) == 1


def test_cancel_before_run_skips_runner(home: Path, page: Path) -> None:
    script = Script()
    runner = Flow(load_config(home), runners=script.runner)
    runner._nodes.cancelled.set()
    nodes = runner._nodes
    command = nodes.run({"runs_this_message": 0})
    assert command.update == {"result_status": "cancelled"}
    assert script.calls == []


def test_cancel_during_run_stops_runner(home: Path, page: Path) -> None:
    script = Script()
    runners: list[FakeRunner] = []
    holder: dict = {}

    def act(page_dir: Path) -> None:
        holder["flow"].cancel()
        return "cancelled"

    script.acts.append(act)

    def make(name, cfg):
        runner = FakeRunner(name, script)
        runners.append(runner)
        return runner

    holder["flow"] = Flow(load_config(home), runners=make)
    result = holder["flow"].start(page.name, "구현해줘")

    assert result.state["result_status"] == "cancelled"
    assert runners[0].cancelled
    assert len(script.calls) == 1


# 명령줄


def test_run_flow_command(
    home: Path, page: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = Script(set_status("blocked"), set_status("blocked"))
    monkeypatch.setattr(
        cli,
        "Flow",
        lambda cfg, on_event: Flow(
            cfg, runners=script.runner, on_event=on_event
        ),
    )
    invoke = CliRunner().invoke
    base = ["--home", str(home)]
    result = invoke(cli.app, ["run", page.name, "오타 고쳐줘", "--flow", *base])
    assert result.exit_code == 1, result.output
    last = result.output.strip().splitlines()[-1]
    thread = f"{page.name}/b01"
    assert last == (
        f"flow {thread} · kind small · runs 2 · last run 2"
        " · waiting blocked · options retry|stop"
    )
    assert "run.started" in result.output and "flow.waiting" in result.output

    result = invoke(cli.app, ["resume", thread, "stop", *base])
    assert result.exit_code == 1, result.output
    assert result.output.strip().endswith("· blocked")
    result = invoke(cli.app, ["resume", thread, "stop", *base])
    assert result.exit_code == 1 and "not waiting" in result.output

    result = invoke(
        cli.app, ["run", page.name, "x", "--flow", "--tool", "claude", *base]
    )
    assert result.exit_code == 1 and "--flow" in result.output
    result = invoke(cli.app, ["run", page.name, "x", *base])
    assert result.exit_code == 1 and "required" in result.output


def test_failed_review_run_asks_human(home: Path, page: Path) -> None:
    script = Script(set_status("review"), runner_error, set_status("review"))
    result = flow(home, script).start(page.name, "구현해줘")

    assert result.waiting["reason"] == "review_failed"
    assert result.waiting["retry"] == "review_run"
    done = flow(home, script).resume(result.thread_id, "retry")
    assert done.state["result_status"] == "done"
    assert [c["name"] for c in script.calls] == ["codex", "claude", "claude"]


def test_retry_after_failed_repair_is_judged_as_implementation(
    home: Path, page: Path
) -> None:
    # 리뷰 실행이 ledger.md를 깨고 보정도 실패한 뒤, 사람이 다시 시도하면
    # 새 구현 실행은 리뷰로 판정되지 않고 다시 리뷰를 받는다.
    script = Script(
        set_status("review"),
        break_state,
        break_state,
        restore_state("review"),
        set_status("review"),
    )
    result = flow(home, script).start(page.name, "구현해줘")
    assert result.waiting["reason"] == "repair_failed"
    assert result.state["last_run_kind"] == "review"

    done = flow(home, script).resume(result.thread_id, "retry")
    assert done.state["result_status"] == "done"
    assert [c["name"] for c in script.calls] == [
        "codex",
        "claude",
        "claude",
        "codex",
        "claude",
    ]
    assert record(page, 5)["kind"] == "review"


def test_waiting_on_lists_paused_flows_of_a_page(
    home: Path, page: Path
) -> None:
    script = Script()
    runner = flow(home, script)
    assert runner.waiting_on(page.name) == []

    first = runner.start(page.name, "구조를 검토해줘")
    second = runner.start(page.name, "구조를 점검해줘")
    other = pages.create_page(page.parent, "다른", slug="other")
    runner.start(other.name, "구조를 검토해줘")

    found = runner.waiting_on(page.name)
    assert [thread for thread, _ in found] == [
        first.thread_id,
        second.thread_id,
    ]
    assert found[0][1]["reason"] == "kind"
