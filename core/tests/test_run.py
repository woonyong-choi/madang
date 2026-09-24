import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import FAKE_CLI, STREAMS
from typer.testing import CliRunner

from madang.cli import app, execute_run
from madang.config import load_config
from madang.graph.steps import environment, run_commit_message
from madang.runners.base import RunResult, Usage
from madang.store import frontmatter, pages
from madang.store.home import init_home

cli_runner = CliRunner()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


class FakeRunner:
    """에이전트를 대신해 정해진 방식으로 페이지를 고친다."""

    def __init__(self, name: str = "claude", act=None, status="done"):
        self.name = name
        self.act = act or (lambda cwd, page_dir: None)
        self.status = status
        self.calls: list[dict] = []

    def exec(self, **kw) -> RunResult:
        kw["by"] = os.environ.get("MADANG_BY")
        self.calls.append(kw)
        page_dir = kw["events_log"].parent.parent
        self.act(kw["cwd"], page_dir)
        return RunResult(
            status=self.status,
            usage=Usage(input=30100, cached=21000, output=640),
            final_text=f"ANSWER-{len(self.calls)}",
            duration=1.5,
            error=None if self.status == "done" else "boom",
        )


def write_design(cwd: Path, page_dir: Path) -> None:
    (page_dir / "blocks/b05-design.md").write_text("# design\n")
    (page_dir / "blocks/b06-notes.md").write_text("stray\n")
    state = page_dir / "state.md"
    header, body = frontmatter.read(state)
    header["status"] = "review"
    header["artifacts"] = ["blocks/b05-design.md"]
    state.write_text(frontmatter.dumps(header, body))


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("MADANG_BY", raising=False)
    for key in ("FAKE_STREAM", "FAKE_DUMP", "FAKE_SLEEP", "FAKE_EXIT"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    init_home(root)
    return root


@pytest.fixture
def page(home: Path) -> Path:
    return pages.create_page(home, "root", "이력서", slug="resume")


def run(page: Path, home: Path, runner: FakeRunner, **kw):
    args = {"model": "m-1", "effort": "medium", "request": "설계해줘"}
    args.update(kw)
    return execute_run(page, runner, cfg=load_config(home), **args)


def record(page: Path, n: int) -> dict:
    return json.loads((page / f"runs/{n}.json").read_text())


def test_run_records_checks_and_commits(home: Path, page: Path) -> None:
    runner = FakeRunner(act=write_design)
    outcome = run(page, home, runner)
    assert outcome.ok and outcome.commit

    data = record(page, 1)
    assert data["trigger"] == {"message": "b01", "target": "page"}
    assert data["runner"] == "claude" and data["model"] == "m-1"
    assert data["kind"] == "build" and data["tier"] == 1
    assert data["contract"] == "v1"
    parts = data["input"]["parts"]
    assert list(parts) == [
        "system_est",
        "root",
        "space",
        "state",
        "contract",
        "request",
    ]
    assert data["input"]["total_est"] == sum(parts.values())
    assert data["usage"] == {"input": 30100, "cached": 21000, "output": 640}
    assert data["changed_files"] == [
        "blocks/b05-design.md",
        "blocks/b06-notes.md",
        "state.md",
    ]
    assert data["unknown_files"] == ["blocks/b06-notes.md"]
    assert data["result_status"] == "review"
    assert data["state_check"] == {"ok": True, "issues": []}
    assert data["duration"] == 1.5

    subject = git(home, "log", "-1", "--format=%s").strip()
    assert subject == (
        "[" + page.name + "] run 1 · claude/m-1 · "
        "blocks/b05-design.md, blocks/b06-notes.md, state.md"
    )
    assert git(home, "rev-parse", "--short", "HEAD").strip() == outcome.commit
    assert git(home, "log", "--format=%s").count("\n") == 2
    assert git(home, "status", "--porcelain") == ""
    tracked = git(home, "ls-files", str(page)).split()
    rel = page.relative_to(home).as_posix()
    assert f"{rel}/runs/.last" in tracked
    assert f"{rel}/runs/1.json" in tracked
    assert not any("/scratch/" in p for p in tracked)
    assert (page / "scratch/b01.prompt.md").read_text() == (
        runner.calls[0]["prompt"]
    )


def test_run_logs_user_and_agent_blocks(home: Path, page: Path) -> None:
    run(page, home, FakeRunner(act=write_design))
    log = (page / "log.md").read_text()
    heads = [line for line in log.splitlines() if line.startswith("<!--")]
    assert len(heads) == 2
    assert heads[0].startswith("<!-- b01 | ") and heads[0].endswith(
        "| user | target=page -->"
    )
    assert heads[1].startswith("<!-- b07 | ")
    assert heads[1].endswith("| agent | run=1 -->")
    assert "설계해줘" in log and "ANSWER-1" in log
    blocks = pages.read_header(page / "page.md")["blocks"]
    assert blocks == ["b01", "b07"]


def test_runner_gets_fresh_session_inputs(home: Path, page: Path) -> None:
    runner = FakeRunner()
    run(page, home, runner, request="first")
    run(page, home, runner, request="second")
    first, second = runner.calls
    assert first["cwd"] == page and first["page"] == page.name
    assert first["by"] == "claude/m-1"
    assert "MADANG_BY" not in os.environ
    # 이전 답변은 다음 프롬프트에 전달되지 않는다
    assert "ANSWER-1" not in second["prompt"]
    assert "first" not in second["prompt"]
    assert "second" in second["prompt"]
    assert record(page, 2)["trigger"]["message"] == "b03"
    assert git(home, "log", "--format=%s").count("\n") == 3


def test_target_and_promoted_tier(home: Path, page: Path) -> None:
    (page / "blocks/b02-cv.md").write_text("CV-BODY\n")
    state = page / "state.md"
    header, body = frontmatter.read(state)
    header["tier"] = 2
    state.write_text(frontmatter.dumps(header, body + "LOG-LINE\n"))
    runner = FakeRunner()
    run(page, home, runner, target="b02")
    prompt = runner.calls[0]["prompt"]
    assert "CV-BODY" in prompt and "LOG-LINE" not in prompt
    data = record(page, 1)
    assert data["tier"] == 2
    assert data["trigger"] == {"message": "b03", "target": "b02"}
    assert "target" in data["input"]["parts"]


def test_missing_target_stops_before_logging(home: Path, page: Path) -> None:
    with pytest.raises(ValueError, match="b09"):
        run(page, home, FakeRunner(), target="b09")
    assert (page / "log.md").read_text() == ""


def test_codex_runner_path(home: Path, page: Path) -> None:
    runner = FakeRunner(name="codex")
    outcome = run(page, home, runner, model="gpt-6-sol")
    data = record(page, 1)
    assert data["runner"] == "codex"
    assert data["input"]["parts"]["system_est"] == 24000
    assert runner.calls[0]["by"] == "codex/gpt-6-sol"
    subject = git(home, "log", "-1", "--format=%s").strip()
    assert subject == f"[{page.name}] run 1 · codex/gpt-6-sol · no file changes"
    assert outcome.ok


def test_code_repository_changes(home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-q")
    pages.create_space(home, "work", repo=str(repo))
    page_dir = pages.create_page(home, "work", "Task", slug="task")

    def act(cwd: Path, page_dir: Path) -> None:
        (cwd / "src").mkdir()
        (cwd / "src/app.py").write_text("print(1)\n")
        (cwd / "src/extra.py").write_text("print(2)\n")
        state = page_dir / "state.md"
        header, body = frontmatter.read(state)
        header["artifacts"] = ["repo:src/app.py"]
        state.write_text(frontmatter.dumps(header, body))

    runner = FakeRunner(act=act)
    outcome = run(page_dir, home, runner)
    assert runner.calls[0]["cwd"] == repo
    data = record(page_dir, 1)
    assert data["changed_files"] == [
        "state.md",
        "repo:src/app.py",
        "repo:src/extra.py",
    ]
    assert data["unknown_files"] == ["repo:src/extra.py"]
    assert outcome.ok
    # 새 space는 첫 run과 함께 커밋된다
    assert "spaces/work/space.md" in git(home, "ls-files").split()


def test_failed_run_is_still_recorded(home: Path, page: Path) -> None:
    outcome = run(page, home, FakeRunner(status="error"))
    assert not outcome.ok
    data = record(page, 1)
    assert data["result_status"] == "error"
    assert data["error"] == "boom"
    assert "error: boom" in (page / "log.md").read_text()
    assert git(home, "status", "--porcelain") == ""


def test_invalid_state_is_reported(home: Path, page: Path) -> None:
    def break_state(cwd: Path, page_dir: Path) -> None:
        (page_dir / "state.md").write_text("---\nstatus: nope\n---\n")

    outcome = run(page, home, FakeRunner(act=break_state))
    assert not outcome.ok and outcome.issues
    check = record(page, 1)["state_check"]
    assert check["ok"] is False and check["issues"]


def test_commit_message_summary() -> None:
    files = ["a", "b", "c", "d", "e"]
    assert run_commit_message("p", 3, "claude", "m", files) == (
        "[p] run 3 · claude/m · a, b +3 more"
    )
    assert run_commit_message("p", 1, "codex", "m", ["a"]) == (
        "[p] run 1 · codex/m · a"
    )


# 명령줄


def use_fake_cli(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = {
        "claude": {
            "bin": sys.executable,
            "args": [str(FAKE_CLI), "--model", "{model}"],
        }
    }
    (home / "config/runners.yaml").write_text(yaml.safe_dump(spec))
    monkeypatch.setenv("FAKE_STREAM", str(STREAMS / "claude-ok.jsonl"))


def test_run_command(
    home: Path, page: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_fake_cli(home, monkeypatch)
    result = cli_runner.invoke(
        app,
        [
            "run",
            page.name,
            "--tool",
            "claude",
            "--model",
            "claude-sonnet-5",
            "--effort",
            "low",
            "요청",
            "--home",
            str(home),
        ],
    )
    assert result.exit_code == 0, result.output
    line = result.output.strip().splitlines()[-1]
    assert line.startswith("run 1 · claude/claude-sonnet-5 · done · input est ")
    assert " / actual " in line and "commit " in line
    assert record(page, 1)["effort"] == "low"


def test_run_command_errors(home: Path, page: Path) -> None:
    base = ["run", "--home", str(home), "--model", "m"]
    result = cli_runner.invoke(app, [*base, "nope", "x", "--tool", "claude"])
    assert result.exit_code == 1 and "not found" in result.output
    result = cli_runner.invoke(app, [*base, page.name, "x", "--tool", "gpt"])
    assert result.exit_code == 1 and "unknown runner" in result.output


def test_page_and_space_new(home: Path) -> None:
    result = cli_runner.invoke(
        app,
        ["space", "new", "work", "--title", "Work", "--home", str(home)],
    )
    assert result.exit_code == 0 and result.output.strip() == "work"
    result = cli_runner.invoke(
        app,
        [
            "page",
            "new",
            "--space",
            "work",
            "--title",
            "이력서",
            "--kind",
            "design",
            "--home",
            str(home),
        ],
    )
    assert result.exit_code == 0, result.output
    page_id = result.output.strip()
    assert page_id.endswith("-이력서")
    page_dir = home / "spaces/work/pages" / page_id
    assert pages.read_header(page_dir / "state.md")["kind"] == "design"
    result = cli_runner.invoke(
        app,
        ["page", "new", "--title", "x", "--kind", "bad", "--home", str(home)],
    )
    assert result.exit_code == 1 and "unknown kind" in result.output


def test_environment_is_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MADANG_BY", "human")
    with environment("MADANG_BY", "claude/x"):
        assert os.environ["MADANG_BY"] == "claude/x"
    assert os.environ["MADANG_BY"] == "human"
