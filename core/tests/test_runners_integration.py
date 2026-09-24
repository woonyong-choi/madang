"""Real CLI runs. Excluded by default; run with ``pytest -m integration``."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from madang.config import load_config
from madang.runners import make_runner
from madang.runners.record import run_page
from madang.store import runs

pytestmark = pytest.mark.integration

PROMPT = "Reply with exactly: ok"

# Same commands as the bundled runners.yaml, plus options that keep the input
# small: no tools, no user settings or MCP servers, a one-line system prompt.
RUNNERS = {
    "claude": {
        "bin": "claude",
        "args": [
            "-p", "--output-format", "stream-json", "--verbose",
            "--model", "{model}", "--effort", "{effort}",
            "--tools", "", "--strict-mcp-config", "--setting-sources", "",
            "--system-prompt", "Follow the user's instruction.",
        ],
    },
    "codex": {
        "bin": "codex",
        "args": [
            "exec", "--json", "--skip-git-repo-check", "--add-dir", "{home}",
            "-m", "{model}", "-c", "model_reasoning_effort={effort}",
        ],
    },
}


def logged_in(tool: str) -> bool:
    if shutil.which(tool) is None:
        return False
    cmd = [tool, "auth", "status"] if tool == "claude" else [tool, "login", "status"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (done.stdout + done.stderr).lower()
    return done.returncode == 0 and "not logged in" not in output


@pytest.fixture
def page_dir(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config" / "runners.yaml").write_text(yaml.safe_dump(RUNNERS), encoding="utf-8")
    page = home / "spaces" / "root" / "pages" / "2026-09-24-ok"
    page.mkdir(parents=True)
    return page


def check(tool: str, model: str, page_dir: Path) -> runs.RunRecord:
    home = page_dir.parents[3]
    config = load_config(home)
    run = run_page(
        make_runner(tool, config), config=config, page_dir=page_dir, cwd=page_dir,
        prompt=PROMPT, model=model, effort="low", kind="small",
    )
    result = run.result
    types = [e.type for e in result.events]
    print(f"{tool} {model}: status={result.status} usage={result.usage} "
          f"duration={result.duration}s text={result.final_text!r}")

    assert result.status == "done", result.error
    assert types[-1] == "done"
    assert "usage" in types and "text" in types
    assert result.final_text.strip().strip(".").lower() == "ok"
    assert result.usage.input > 0 and result.usage.output > 0
    assert runs.events_path(page_dir, run.n).stat().st_size > 0
    record = runs.read_run(page_dir, run.n)
    assert record.result_status == "done"
    assert record.usage.input == result.usage.input
    return record


def test_claude_reply_ok(page_dir: Path) -> None:
    if not logged_in("claude"):
        pytest.skip("claude is not installed or not logged in")
    record = check("claude", "claude-haiku-4-5", page_dir)
    assert record.usage.input <= 5000


def test_codex_reply_ok(page_dir: Path) -> None:
    if not logged_in("codex"):
        pytest.skip("codex is not installed or not logged in")
    check("codex", "gpt-6-luna", page_dir)
