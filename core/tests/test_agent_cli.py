import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from madang.cli import app
from madang.store import frontmatter, git, pages
from madang.store.home import init_home

PAGE_ID = "2026-09-24-lock"
runner = CliRunner()


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@dataclass
class Env:
    home: Path
    page: Path
    repo: Path

    def state(self) -> dict:
        return frontmatter.read(self.page / "state.md")[0]

    def page_header(self) -> dict:
        return frontmatter.read(self.page / "page.md")[0]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("MADANG_BY", raising=False)
    monkeypatch.delenv("MADANG_TEMPLATES", raising=False)

    home = tmp_path / "home"
    init_home(home)
    repo = tmp_path / "code"
    repo.mkdir()
    sh(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("code\n")
    sh(repo, "add", "README.md")
    git.commit(repo, "init")

    pages.create_space(home, "work", title="Work", repo=str(repo))
    page = pages.create_page(home, "work", "lock", day=date(2026, 9, 24))
    git.add(home, ["spaces"])
    git.commit(home, "fixture")
    monkeypatch.setenv("MADANG_HOME", str(home))
    monkeypatch.setenv("MADANG_PAGE", PAGE_ID)
    return Env(home=home, page=page, repo=repo)


def invoke(*args: str):
    return runner.invoke(app, list(args))


def ok(*args: str):
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    return result


def refused(*args: str, match: str = ""):
    result = invoke(*args)
    assert result.exit_code == 1, result.output
    assert match in result.output
    return result


# page selection


def test_refuses_without_page(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MADANG_PAGE")
    for args in (
        ["task", "T1", "--status", "doing", "--title", "x"],
        ["decide", "D1", "--topic", "t", "--choice", "a", "--options", "a,b"],
        ["artifact", "add", "blocks/x.md"],
        ["commit", "-m", "x"],
        ["push"],
        ["promote", "b01"],
        ["view", "create", "--template", "table", "--data", "b01"],
    ):
        refused(*args, match="MADANG_PAGE is not set")
    ok("task", "T1", "--status", "doing", "--title", "x", "--page", PAGE_ID)
    assert env.state()["tasks"] == [
        {"id": "T1", "title": "x", "status": "doing"}
    ]


def test_home_option_and_unknown_page(env: Env, tmp_path: Path) -> None:
    refused(
        "task",
        "T1",
        "--status",
        "doing",
        "--title",
        "x",
        "--page",
        "2026-01-01-none",
        match="not found",
    )
    refused(
        "task",
        "T1",
        "--status",
        "doing",
        "--title",
        "x",
        "--home",
        str(tmp_path / "nohome"),
        match="does not exist",
    )
    ok(
        "task",
        "T1",
        "--status",
        "doing",
        "--title",
        "x",
        "--home",
        str(env.home),
    )


def test_app_home_is_not_committed(env: Env) -> None:
    before = git.log_oneline(env.home)
    ok("task", "T1", "--status", "doing", "--title", "x")
    ok("decide", "D1", "--topic", "t", "--choice", "a", "--options", "a,b")
    assert git.log_oneline(env.home) == before


# task


def test_task_add_and_update(env: Env) -> None:
    body = (env.page / "state.md").read_text().split("---\n", 2)[2]
    ok("task", "T1", "--status", "todo", "--title", "원인 분석")
    ok("task", "T1", "--status", "done", "--due", "2026-09-26")
    ok("task", "T2", "--status", "doing", "--title", "잠금")
    assert env.state()["tasks"] == [
        {
            "id": "T1",
            "title": "원인 분석",
            "status": "done",
            "due": date(2026, 9, 26),
        },
        {"id": "T2", "title": "잠금", "status": "doing"},
    ]
    assert (env.page / "state.md").read_text().endswith(body)


def test_task_refusals(env: Env) -> None:
    before = (env.page / "state.md").read_bytes()
    refused("task", "T9", "--status", "doing", match="pass --title")
    refused(
        "task",
        "T1",
        "--status",
        "finished",
        "--title",
        "x",
        match="is not one of",
    )
    refused(
        "task",
        "T1",
        "--status",
        "doing",
        "--title",
        "x",
        "--due",
        "tomorrow",
        match="YYYY-MM-DD",
    )
    refused(
        "task",
        "bad id",
        "--status",
        "doing",
        "--title",
        "x",
        match="invalid task id",
    )
    assert (env.page / "state.md").read_bytes() == before


def test_write_rolled_back_when_page_is_invalid(env: Env) -> None:
    state = env.page / "state.md"
    state.write_text(state.read_text().replace("## 다음 할 일", "## 다른 절"))
    before = state.read_bytes()
    result = refused(
        "task", "T1", "--status", "doing", "--title", "x", match="rolled back"
    )
    assert "missing-section" in result.output
    assert state.read_bytes() == before


# decide


def test_decide_and_supersede(env: Env) -> None:
    (env.page / "runs").mkdir()
    (env.page / "runs" / ".last").write_text("3\n")
    ok(
        "decide",
        "D1",
        "--topic",
        "갱신 경합",
        "--choice",
        "refresh-lock",
        "--options",
        "refresh-lock, sliding-session",
    )
    ok(
        "decide",
        "D2",
        "--topic",
        "갱신 경합",
        "--choice",
        "client-retry",
        "--options",
        "refresh-lock,client-retry",
        "--supersedes",
        "D1",
        "--by",
        "claude/claude-opus-5-5",
    )
    d1, d2 = env.state()["decisions"]
    assert d1 == {
        "id": "D1",
        "topic": "갱신 경합",
        "choice": "refresh-lock",
        "options": ["refresh-lock", "sliding-session"],
        "by": "agent",
        "run": 3,
        "state": "superseded",
        "supersedes": None,
    }
    assert (
        d2["state"] == "confirmed"
        and d2["supersedes"] == "D1"
        and d2["by"] == "claude/claude-opus-5-5"
    )


def test_decide_by_human_has_no_run(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MADANG_PAGE")
    ok(
        "decide",
        "D1",
        "--topic",
        "t",
        "--choice",
        "a",
        "--options",
        "a,b",
        "--page",
        PAGE_ID,
    )
    decision = env.state()["decisions"][0]
    assert decision["by"] == "human" and decision["run"] is None


def test_decide_refusals(env: Env) -> None:
    ok("decide", "D1", "--topic", "t", "--choice", "a", "--options", "a,b")
    before = (env.page / "state.md").read_bytes()
    refused(
        "decide",
        "D2",
        "--topic",
        "t",
        "--choice",
        "c",
        "--options",
        "a,b",
        match="not in options",
    )
    refused(
        "decide",
        "D1",
        "--topic",
        "t",
        "--choice",
        "a",
        "--options",
        "a,b",
        match="already exists",
    )
    refused(
        "decide",
        "D2",
        "--topic",
        "t",
        "--choice",
        "a",
        "--options",
        "a,b",
        "--supersedes",
        "D9",
        match="does not exist",
    )
    refused(
        "decide",
        "D2",
        "--topic",
        "t",
        "--choice",
        "a",
        "--options",
        ",",
        match="at least one",
    )
    refused(
        "decide",
        "D2",
        "--topic",
        "t",
        "--choice",
        "a",
        "--options",
        "a,b",
        "--state",
        "maybe",
        match="is not one of",
    )
    assert (env.page / "state.md").read_bytes() == before


# artifact


def test_artifact_add(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    (env.page / "blocks" / "b01-race.md").write_text("분석\n")
    (env.repo / "src").mkdir()
    (env.repo / "src" / "lock.ts").write_text("export {}\n")
    ok("artifact", "add", "blocks/b01-race.md")
    ok("artifact", "add", str(env.repo / "src" / "lock.ts"))
    monkeypatch.chdir(env.repo)
    result = ok("artifact", "add", "src/lock.ts")
    assert "already registered" in result.output
    ok("artifact", "add", "repo:README.md")
    assert env.state()["artifacts"] == [
        "blocks/b01-race.md",
        "repo:src/lock.ts",
        "repo:README.md",
    ]


def test_artifact_refusals(env: Env, tmp_path: Path) -> None:
    before = (env.page / "state.md").read_bytes()
    result = refused(
        "artifact", "add", "blocks/missing.md", match="rolled back"
    )
    assert "artifact-missing" in result.output
    refused("artifact", "add", "repo:src/none.ts", match="artifact-missing")
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x")
    refused("artifact", "add", str(outside), match="outside the page folder")
    assert (env.page / "state.md").read_bytes() == before


# commit


def test_commit(env: Env) -> None:
    (env.repo / "a.txt").write_text("a\n")
    result = ok("commit", "-m", "feat: add a")
    assert sh(env.repo, "log", "-1", "--format=%s").strip() == "feat: add a"
    assert sh(env.repo, "rev-parse", "--short", "HEAD").strip() in result.output
    assert sh(env.repo, "status", "--porcelain") == ""


def test_commit_refusals(env: Env) -> None:
    refused("commit", "-m", "nothing", match="nothing to commit")
    (env.repo / "a.txt").write_text("a\n")
    refused("commit", "-m", "  ", match="message is empty")
    (env.repo / ".env").write_text("TOKEN=x\n")
    refused("commit", "-m", "leak", match="may hold secrets: .env")
    assert sh(env.repo, "diff", "--cached", "--name-only") == ""
    assert len(sh(env.repo, "log", "--oneline").splitlines()) == 1


def test_commit_refused_without_repo(env: Env) -> None:
    space = env.home / "spaces" / "work" / "space.md"
    space.write_text(
        space.read_text().replace(f"repo: {env.repo}", "repo: null")
    )
    refused("commit", "-m", "x", match="no code repository")
    refused("push", match="no code repository")
    refused("promote", "b01", match="no code repository")
    space.write_text(
        space.read_text().replace("repo: null", f"repo: {env.home / 'nothing'}")
    )
    refused("commit", "-m", "x", match="does not exist")


# push


def add_remote(env: Env, tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    sh(env.repo, "remote", "add", "origin", str(remote))
    return remote


def test_push_current_branch(env: Env, tmp_path: Path) -> None:
    remote = add_remote(env, tmp_path)
    sh(env.repo, "branch", "other")
    result = ok("push")
    assert "pushed main to origin" in result.output
    assert sh(remote, "rev-parse", "main") == sh(env.repo, "rev-parse", "main")
    assert "other" not in sh(remote, "branch")


def test_push_refusals(env: Env, tmp_path: Path) -> None:
    refused("push", match="no remote")
    remote = add_remote(env, tmp_path)
    ok("push")
    (env.repo / "a.txt").write_text("a\n")
    sh(env.repo, "add", "a.txt")
    git.commit(env.repo, "a")
    sh(env.repo, "push", "-q", "origin", "main")
    pushed = sh(remote, "rev-parse", "main")
    sh(env.repo, "reset", "-q", "--hard", "HEAD~1")
    (env.repo / "b.txt").write_text("b\n")
    sh(env.repo, "add", "b.txt")
    git.commit(env.repo, "b")
    refused("push", match="push to origin/main failed")
    assert sh(remote, "rev-parse", "main") == pushed
    sh(env.repo, "checkout", "-q", "--detach")
    refused("push", match="detached")


# promote


def test_promote(env: Env) -> None:
    (env.page / "blocks" / "b01-race-analysis.md").write_text("# 분석\n")
    result = ok("promote", "b01")
    assert "docs/race-analysis.md" in result.output
    assert (env.repo / "docs" / "race-analysis.md").read_text() == "# 분석\n"
    assert (
        sh(env.repo, "log", "-1", "--format=%s").strip()
        == f"docs: promote b01 from {PAGE_ID}"
    )
    assert sh(env.repo, "status", "--porcelain") == ""
    assert env.state()["artifacts"] == ["repo:docs/race-analysis.md"]
    assert "already up to date" in ok("promote", "b01").output


def test_promote_refusals(env: Env) -> None:
    refused("promote", "b01", match="no file")
    refused("promote", "x1", match="not a block id")
    (env.page / "blocks" / "b01-race.md").write_text("new\n")
    (env.repo / "docs").mkdir()
    (env.repo / "docs" / "race.md").write_text("local edit\n")
    refused("promote", "b01", match="uncommitted changes")
    assert (env.repo / "docs" / "race.md").read_text() == "local edit\n"
    assert env.state()["artifacts"] == []


def test_promote_rolled_back_when_page_is_invalid(env: Env) -> None:
    (env.page / "blocks" / "b01-race.md").write_text("x\n")
    state = env.page / "state.md"
    state.write_text(state.read_text().replace("## 목표", "## 목적"))
    refused("promote", "b01", match="rolled back")
    assert not (env.repo / "docs" / "race.md").exists()
    assert len(sh(env.repo, "log", "--oneline").splitlines()) == 1


# view


def test_view_create(env: Env) -> None:
    (env.page / "runs").mkdir()
    (env.page / "runs" / ".last").write_text("2\n")
    (env.page / "blocks" / "b01-cv.json").write_text("{}")
    (env.page / "blocks" / "b02-extra.json").write_text("{}")
    pages.append_block(env.page, "b01")
    result = ok(
        "view",
        "create",
        "--template",
        "resume",
        "--data",
        "overlay=b02",
        "--data",
        "b01",
    )
    assert "created view b03" in result.output
    header, _ = frontmatter.read(env.page / "blocks" / "b03-resume.view.md")
    assert header == {
        "type": "view",
        "template": "resume@1",
        "bindings": {"base": "b01", "overlay": "b02"},
        "created_by": "run 2",
    }
    assert env.page_header()["blocks"] == ["b01", "b03"]
    ok("view", "create", "--template", "table@1", "--data", "b01")
    assert env.page_header()["blocks"] == ["b01", "b03", "b04"]


def test_view_uses_home_template(env: Env) -> None:
    tpl = env.home / "templates" / "cards"
    tpl.mkdir()
    (tpl / "template.yaml").write_text(
        "name: cards\nversion: 2\nslots:\n  items: {required: true}\n"
    )
    (env.page / "blocks" / "b01-items.csv").write_text("a\n")
    ok("view", "create", "--template", "cards", "--data", "b01")
    assert (
        frontmatter.read(env.page / "blocks" / "b02-cards.view.md")[0][
            "template"
        ]
        == "cards@2"
    )


def test_view_refusals(env: Env) -> None:
    (env.page / "blocks" / "b01-cv.json").write_text("{}")
    (env.page / "blocks" / "b02-note.md").write_text("x")
    before = sorted(p.name for p in (env.page / "blocks").iterdir())
    refused(
        "view",
        "create",
        "--template",
        "nope",
        "--data",
        "b01",
        match="not found",
    )
    refused(
        "view",
        "create",
        "--template",
        "table@3",
        "--data",
        "b01",
        match="version 1",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b09",
        match="not found in blocks/",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b02",
        match="not found in blocks/",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "x=b01",
        match="no slot 'x'",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b01",
        "--data",
        "b01",
        match="too many",
    )
    refused(
        "view",
        "create",
        "--template",
        "resume",
        "--data",
        "overlay=b01",
        match="required slot",
    )
    assert sorted(p.name for p in (env.page / "blocks").iterdir()) == before


def test_view_rolled_back_when_page_is_invalid(env: Env) -> None:
    (env.page / "blocks" / "b01-cv.json").write_text("{}")
    page_md = env.page / "page.md"
    page_md.write_text(
        page_md.read_text().replace("status: planning", "status: nope")
    )
    before = page_md.read_bytes()
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b01",
        match="rolled back",
    )
    assert page_md.read_bytes() == before
    assert not list((env.page / "blocks").glob("*.view.md"))


# help


def test_help() -> None:
    result = ok("help")
    for name in (
        "task",
        "decide",
        "artifact add",
        "commit",
        "push",
        "promote",
        "view create",
        "help",
    ):
        assert f"madang {name}" in result.output
    assert "--supersedes" in ok("help", "decide").output
    assert "--template" in ok("help", "view", "create").output
    refused("help", "nope", match="unknown command")


def test_malformed_state_is_reported(env: Env) -> None:
    (env.page / "state.md").write_text("---\nstatus: [\n---\n## 목표\n")
    refused(
        "task", "T1", "--status", "doing", "--title", "x", match="invalid YAML"
    )
