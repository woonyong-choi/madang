import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import STREAMS

from madang.config import RunnerSpec, load_config
from madang.runners import ClaudeRunner, CodexRunner, RunEvent, make_runner
from madang.runners.base import render_args


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in (
        "FAKE_STREAM",
        "FAKE_DUMP",
        "FAKE_SLEEP",
        "FAKE_CHILD",
        "FAKE_STDERR",
        "FAKE_EXIT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MADANG_PAGE", "leaked-from-parent")
    cwd = tmp_path / "work"
    cwd.mkdir()
    return cwd


def collect() -> tuple[list[RunEvent], Callable[[RunEvent], None]]:
    events: list[RunEvent] = []
    return events, events.append


def test_render_args() -> None:
    values = {"model": "m", "effort": "high", "home": "/h", "page": None}
    assert render_args(
        ["-m", "{model}", "-c", "model_reasoning_effort={effort}"], values
    ) == [
        "-m",
        "m",
        "-c",
        "model_reasoning_effort=high",
    ]
    assert render_args(['{"literal": 1}'], values) == ['{"literal": 1}']
    with pytest.raises(ValueError, match="unknown"):
        render_args(["{nope}"], values)
    with pytest.raises(ValueError, match="no value"):
        render_args(["{page}"], values)


def test_default_commands_come_from_runners_yaml(tmp_path: Path) -> None:
    config = load_config(tmp_path / "home")
    claude = make_runner("claude", config)
    codex = make_runner("codex", config)
    assert isinstance(claude, ClaudeRunner) and isinstance(codex, CodexRunner)

    records = tmp_path / "proj" / ".madang"
    cmd = claude.command(
        cwd=tmp_path,
        prompt="-hi",
        model="claude-haiku-4-5",
        effort="low",
        records=records,
        extra_args=["--disallowedTools", "Bash(git reset --hard)"],
    )
    assert cmd == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "acceptEdits",
        "--add-dir",
        str(records),
        "--allowedTools",
        "Bash(madang *)",
        "--disallowedTools",
        "Bash(git *)",
        "Bash(gh *)",
        "--model",
        "claude-haiku-4-5",
        "--effort",
        "low",
        "--disallowedTools",
        "Bash(git reset --hard)",
        "--",
        "-hi",
    ]
    cmd = codex.command(
        cwd=tmp_path, prompt="hi", model="gpt-6-luna", effort="low"
    )
    assert cmd == [
        "codex",
        "exec",
        "--json",
        "-m",
        "gpt-6-luna",
        "-c",
        "model_reasoning_effort=low",
        "--",
        "hi",
    ]
    for forbidden in ("--resume", "--continue", "resume"):
        assert forbidden not in claude.spec.args + codex.spec.args


def test_prompt_placeholder_and_home_dir(tmp_path: Path) -> None:
    spec = RunnerSpec(
        bin="codex",
        args=["exec", "--add-dir", "{home}", "{prompt}", "-m", "{model}"],
    )
    runner = CodexRunner(spec, home=tmp_path / "home")
    cmd = runner.command(cwd=tmp_path, prompt="go", model="m", effort="low")
    assert cmd == [
        "codex",
        "exec",
        "--add-dir",
        str(tmp_path / "home"),
        "go",
        "-m",
        "m",
    ]


def test_unknown_runner(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown runner"):
        make_runner("gemini", load_config(tmp_path))


def test_exec_replays_stream(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dump = tmp_path / "dump.json"
    monkeypatch.setenv("FAKE_STREAM", str(STREAMS / "claude-tools.jsonl"))
    monkeypatch.setenv("FAKE_DUMP", str(dump))
    home = tmp_path / "home"
    runner = ClaudeRunner(
        fake_spec, home=home, core_url="http://127.0.0.1:7470"
    )
    log = tmp_path / "runs" / "1.jsonl"
    events, on_event = collect()

    result = runner.exec(
        cwd=work,
        prompt="do it",
        model="claude-haiku-4-5",
        effort="low",
        on_event=on_event,
        page="2026-09-24-demo",
        events_log=log,
    )

    assert result.status == "done", result.error
    assert result.exit_code == 0
    assert result.final_text == "Done."
    assert result.usage.output > 0
    assert result.changed_files == ["/work/project/hello.txt"]
    assert result.duration >= 0
    assert events == result.events
    assert events[-1] == RunEvent("done", text="Done.")
    assert log.read_text(encoding="utf-8") == (
        STREAMS / "claude-tools.jsonl"
    ).read_text(encoding="utf-8")

    called = json.loads(dump.read_text(encoding="utf-8"))
    assert called["argv"] == [
        "--model",
        "claude-haiku-4-5",
        "--effort",
        "low",
        "--add-dir",
        str(home),
        "--",
        "do it",
    ]
    assert Path(called["cwd"]).resolve() == work.resolve()
    assert called["env"] == {
        "MADANG_PAGE": "2026-09-24-demo",
        "MADANG_HOME": str(home),
        "MADANG_CORE_URL": "http://127.0.0.1:7470",
    }


def test_exec_without_page_drops_inherited_page(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dump = tmp_path / "dump.json"
    monkeypatch.setenv("FAKE_STREAM", str(STREAMS / "codex-ok.jsonl"))
    monkeypatch.setenv("FAKE_DUMP", str(dump))
    result = CodexRunner(fake_spec, home=tmp_path).exec(
        cwd=work, prompt="p", model="m", effort="low", on_event=lambda e: None
    )
    assert result.status == "done"
    assert "MADANG_PAGE" not in json.loads(dump.read_text())["env"]


def test_exec_error_result(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_STREAM", str(STREAMS / "claude-error.jsonl"))
    monkeypatch.setenv("FAKE_EXIT", "1")
    events, on_event = collect()
    result = ClaudeRunner(fake_spec, home=tmp_path).exec(
        cwd=work,
        prompt="p",
        model="claude-nope-9",
        effort="low",
        on_event=on_event,
    )
    assert result.status == "error"
    assert result.exit_code == 1
    assert "claude-nope-9" in (result.error or "")
    # 파서가 이미 오류를 보고했으므로 반복하지 않는다
    assert [e.type for e in events].count("error") == 1
    assert "done" not in [e.type for e in events]


def test_exec_nonzero_exit_uses_stderr(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_STDERR", "Error: not logged in")
    monkeypatch.setenv("FAKE_EXIT", "2")
    events, on_event = collect()
    result = CodexRunner(fake_spec, home=tmp_path).exec(
        cwd=work, prompt="p", model="m", effort="low", on_event=on_event
    )
    assert result.status == "error"
    assert result.error == "Error: not logged in"
    assert events == [RunEvent("error", message="Error: not logged in")]


def test_exec_stream_without_result_is_error(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truncated = tmp_path / "cut.jsonl"
    truncated.write_text(
        (STREAMS / "codex-ok.jsonl").read_text().splitlines()[0]
        + "\nnot json\n"
    )
    monkeypatch.setenv("FAKE_STREAM", str(truncated))
    result = CodexRunner(fake_spec, home=tmp_path).exec(
        cwd=work, prompt="p", model="m", effort="low", on_event=lambda e: None
    )
    assert result.status == "error"
    assert result.error == "stream ended without a final result"


def test_exec_missing_binary(work: Path, tmp_path: Path) -> None:
    runner = ClaudeRunner(
        RunnerSpec(bin=str(tmp_path / "no-such-cli")), home=tmp_path
    )
    events, on_event = collect()
    result = runner.exec(
        cwd=work, prompt="p", model="m", effort="low", on_event=on_event
    )
    assert result.status == "error"
    assert result.error.startswith("cannot start")
    assert events[0].type == "error"


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _wait_gone(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _gone(pid):
            return True
        time.sleep(0.05)
    return False


def test_timeout_stops_process_group(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_STREAM", str(STREAMS / "codex-ok.jsonl"))
    monkeypatch.setenv("FAKE_SLEEP", "30")
    monkeypatch.setenv("FAKE_CHILD", str(child))
    events, on_event = collect()

    started = time.monotonic()
    result = CodexRunner(fake_spec, home=tmp_path).exec(
        cwd=work,
        prompt="p",
        model="m",
        effort="low",
        on_event=on_event,
        timeout=0.5,
    )

    assert time.monotonic() - started < 10
    assert result.status == "blocked"
    assert result.error == "timed out after 0.5s"
    assert events[-1] == RunEvent("error", message="timed out after 0.5s")
    assert _wait_gone(int(child.read_text()))


def test_cancel(
    work: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "30")
    runner = CodexRunner(fake_spec, home=tmp_path)
    results = []
    thread = threading.Thread(
        target=lambda: results.append(
            runner.exec(
                cwd=work,
                prompt="p",
                model="m",
                effort="low",
                on_event=lambda e: None,
            )
        )
    )
    thread.start()
    deadline = time.monotonic() + 5
    while runner._proc is None and time.monotonic() < deadline:
        time.sleep(0.02)
    time.sleep(0.2)
    runner.cancel()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert results[0].status == "cancelled"
    runner.cancel()  # 남은 프로세스가 없으므로 아무 일도 없다
