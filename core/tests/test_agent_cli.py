import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from madang.api.app import create_app
from madang.cli import app
from madang.cli_agent import client
from madang.store import frontmatter, git, pages, projects
from madang.store.home import init_home

PAGE_ID = "2026-09-24-lock"
LOCAL = "http://127.0.0.1:7470"
runner = CliRunner()
open_http_transport = client.open_transport


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
    core: object

    def state(self) -> dict:
        return frontmatter.read(self.page / "ledger.md")[0]

    def page_header(self) -> dict:
        return frontmatter.read(self.page / "page.md")[0]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    project = projects.add(home, repo, project_id="work", title="Work")
    page = pages.create_page(project.pages_dir, "lock", day=date(2026, 9, 24))
    monkeypatch.setenv("MADANG_HOME", str(home))
    monkeypatch.setenv("MADANG_PAGE", PAGE_ID)
    monkeypatch.delenv("MADANG_CORE_URL", raising=False)

    # 명령은 core를 부른다. 앱을 같은 프로세스에서 띄워 그리로 보낸다.
    api = create_app(home)

    def transport(method: str, path: str, payload):
        response = http.request(method, path, json=payload)
        return (
            response.status_code,
            response.json() if response.content else None,
        )

    with TestClient(api, base_url=LOCAL) as http:
        monkeypatch.setattr(client, "open_transport", lambda _home: transport)
        yield Env(home=home, page=page, repo=repo, core=api.state.core)


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


# 페이지 선택


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
        ["view", "create", "--template", "table", "--data", "b01"],
    ):
        refused(*args, match="MADANG_PAGE가 설정돼 있지 않다")
    ok("task", "T1", "--status", "doing", "--title", "x", "--page", PAGE_ID)
    assert env.state()["tasks"] == [
        {"id": "T1", "title": "x", "status": "doing"}
    ]


def test_unknown_page(env: Env) -> None:
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


def test_core_address_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "addr"
    home.mkdir()
    monkeypatch.delenv("MADANG_CORE_URL", raising=False)
    assert client.core_url(home) == client.DEFAULT_URL
    (home / "core.port").write_text("7481\n")
    assert client.core_url(home) == "http://127.0.0.1:7481"
    monkeypatch.setenv("MADANG_CORE_URL", "http://127.0.0.1:9000/")
    assert client.core_url(home) == "http://127.0.0.1:9000"


def test_home_option_is_used_to_find_core(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path | None] = []
    open_in_process = client.open_transport
    monkeypatch.setattr(
        client,
        "open_transport",
        lambda home: seen.append(home) or open_in_process(home),
    )
    ok("task", "T1", "--status", "doing", "--title", "x")
    ok(
        "task",
        "T2",
        "--status",
        "doing",
        "--title",
        "y",
        "--home",
        str(env.home),
    )
    assert seen == [None, env.home]


def test_unreachable_core_exits_with_2(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client, "open_transport", open_http_transport)
    monkeypatch.setenv("MADANG_CORE_URL", "http://127.0.0.1:1")
    result = invoke("push")
    assert result.exit_code == 2, result.output
    assert "연결할 수 없다" in result.output
    assert "madang serve" in result.output


def test_ledger_changes_are_not_committed(env: Env) -> None:
    ok("task", "T1", "--status", "doing", "--title", "x")
    ok("decide", "D1", "--topic", "t", "--choice", "a", "--options", "a,b")
    assert env.state()["tasks"][0]["id"] == "T1"
    assert not (env.home / ".git").exists()
    assert len(sh(env.repo, "log", "--oneline").splitlines()) == 1
    assert sh(env.repo, "status", "--porcelain") == ""


# 과업


def test_task_add_and_update(env: Env) -> None:
    body = (env.page / "ledger.md").read_text().split("---\n", 2)[2]
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
    assert (env.page / "ledger.md").read_text().endswith(body)


def test_task_refusals(env: Env) -> None:
    before = (env.page / "ledger.md").read_bytes()
    refused("task", "T9", "--status", "doing", match="title이 필요하다")
    refused(
        "task",
        "T1",
        "--status",
        "finished",
        "--title",
        "x",
        match="status",
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
        match="YYYY-MM-DD 날짜가 아니다",
    )
    refused(
        "task",
        "bad id",
        "--status",
        "doing",
        "--title",
        "x",
        match="잘못된 태스크 id",
    )
    assert (env.page / "ledger.md").read_bytes() == before


def test_write_rolled_back_when_page_is_invalid(env: Env) -> None:
    state = env.page / "ledger.md"
    state.write_text(state.read_text().replace("## 다음 할 일", "## 다른 절"))
    before = state.read_bytes()
    result = refused(
        "task", "T1", "--status", "doing", "--title", "x", match="되돌렸다"
    )
    assert "missing-section" in result.output
    assert state.read_bytes() == before


# 결정


def test_decide_and_supersede(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    (env.page / "runs").mkdir()
    (env.page / "runs" / ".last").write_text("3\n")
    monkeypatch.setattr(env.core.flows, "busy", lambda page: True)
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
    (env.page / "runs").mkdir()
    (env.page / "runs" / ".last").write_text("3\n")
    monkeypatch.setattr(env.core.flows, "busy", lambda page: True)
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

    (env.page / "blocks" / "b01-cv.json").write_text("{}")
    ok(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b01",
        "--page",
        PAGE_ID,
    )
    header, _ = frontmatter.read(env.page / "blocks" / "b02-table.view.md")
    assert "created_by" not in header


def test_decide_refusals(env: Env) -> None:
    ok("decide", "D1", "--topic", "t", "--choice", "a", "--options", "a,b")
    before = (env.page / "ledger.md").read_bytes()
    refused(
        "decide",
        "D2",
        "--topic",
        "t",
        "--choice",
        "c",
        "--options",
        "a,b",
        match="에 없다",
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
        match="이미 있다",
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
        match="대체할 결정",
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
        match="하나 이상",
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
        match="state",
    )
    assert (env.page / "ledger.md").read_bytes() == before


# 산출물


def test_artifact_add(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    (env.page / "blocks" / "b01-race.md").write_text("분석\n")
    (env.repo / "src").mkdir()
    (env.repo / "src" / "lock.ts").write_text("export {}\n")
    ok("artifact", "add", "blocks/b01-race.md")
    ok("artifact", "add", str(env.repo / "src" / "lock.ts"))
    monkeypatch.chdir(env.repo)
    ok("artifact", "add", "src/lock.ts")
    ok("artifact", "add", "repo:README.md")
    assert env.state()["artifacts"] == [
        "blocks/b01-race.md",
        "repo:src/lock.ts",
        "repo:README.md",
    ]


def test_artifact_refusals(env: Env, tmp_path: Path) -> None:
    before = (env.page / "ledger.md").read_bytes()
    result = refused("artifact", "add", "blocks/missing.md", match="되돌렸다")
    assert "artifact-missing" in result.output
    refused("artifact", "add", "repo:src/none.ts", match="artifact-missing")
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x")
    refused("artifact", "add", str(outside), match="밖에 있다")
    assert (env.page / "ledger.md").read_bytes() == before


def test_artifact_add_rejects_parent_paths(
    env: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = (env.page / "ledger.md").read_bytes()
    (tmp_path / "outside.md").write_text("x\n")
    refused("artifact", "add", "../outside.md", match="상위 폴더")
    refused("artifact", "add", "repo:../x", match="상위 폴더")
    monkeypatch.chdir(env.page)
    refused("artifact", "add", "../../../../outside.md", match="밖에 있다")
    assert (env.page / "ledger.md").read_bytes() == before


# 커밋


def test_commit(env: Env) -> None:
    (env.repo / "a.txt").write_text("a\n")
    result = ok("commit", "-m", "feat: add a")
    assert sh(env.repo, "log", "-1", "--format=%s").strip() == "feat: add a"
    assert sh(env.repo, "rev-parse", "--short", "HEAD").strip() in result.output
    assert sh(env.repo, "status", "--porcelain") == ""


def test_commit_refusals(env: Env) -> None:
    refused("commit", "-m", "nothing", match="커밋할 변경이 없다")
    (env.repo / "a.txt").write_text("a\n")
    refused("commit", "-m", "  ", match="메시지가 비어 있다")
    (env.repo / ".env").write_text("TOKEN=x\n")
    refused(
        "commit",
        "-m",
        "leak",
        match="비밀이 들어 있을 수 있는 파일은 커밋하지 않는다: .env",
    )
    assert sh(env.repo, "diff", "--cached", "--name-only") == ""
    assert len(sh(env.repo, "log", "--oneline").splitlines()) == 1


def test_commit_refused_without_repo(env: Env) -> None:
    shutil.rmtree(env.repo / ".git")
    (env.page / "blocks" / "b01-x.md").write_text("x\n")
    refused("commit", "-m", "x", match="git 저장소가 아니다")
    refused("push", match="git 저장소가 아니다")


# 푸시


def add_remote(env: Env, tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    sh(env.repo, "remote", "add", "origin", str(remote))
    return remote


def test_push_current_branch(env: Env, tmp_path: Path) -> None:
    remote = add_remote(env, tmp_path)
    sh(env.repo, "branch", "other")
    result = ok("push")
    assert "푸시했다: main -> origin" in result.output
    assert sh(remote, "rev-parse", "main") == sh(env.repo, "rev-parse", "main")
    assert "other" not in sh(remote, "branch")


def test_push_refusals(env: Env, tmp_path: Path) -> None:
    refused("push", match="리모트가 없다")
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
    refused("push", match="origin/main 푸시에 실패했다")
    assert sh(remote, "rev-parse", "main") == pushed
    sh(env.repo, "checkout", "-q", "--detach")
    refused("push", match="분리")


# 보기


def test_view_create(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    (env.page / "runs").mkdir()
    (env.page / "runs" / ".last").write_text("2\n")
    monkeypatch.setattr(env.core.flows, "busy", lambda page: True)
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
    assert "뷰 b03 생성" in result.output
    header, _ = frontmatter.read(env.page / "blocks" / "b03-resume.view.md")
    assert header == {
        "type": "view",
        "template": "resume@1",
        "bindings": {"base": "b01", "overlay": "b02"},
        "created_by": "run 2",
    }
    assert env.state()["artifacts"] == ["blocks/b03-resume.view.md"]
    assert env.page_header()["blocks"] == ["b01", "b03"]
    ok("view", "create", "--template", "table@1", "--data", "b01")
    assert env.page_header()["blocks"] == ["b01", "b03", "b04"]


def test_view_uses_home_template(env: Env) -> None:
    tpl = env.home / "templates" / "cards"
    tpl.mkdir(parents=True)
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
        match="이 없다",
    )
    refused(
        "view",
        "create",
        "--template",
        "table@3",
        "--data",
        "b01",
        match="버전 1",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b09",
        match="blocks/에 없다",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "b02",
        match="blocks/에 없다",
    )
    refused(
        "view",
        "create",
        "--template",
        "table",
        "--data",
        "x=b01",
        match="슬롯 'x'이 없다",
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
        match="너무 많다",
    )
    refused(
        "view",
        "create",
        "--template",
        "resume",
        "--data",
        "overlay=b01",
        match="필수 슬롯",
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
        match="되돌렸다",
    )
    assert page_md.read_bytes() == before
    assert not list((env.page / "blocks").glob("*.view.md"))


# 도움말


def test_help() -> None:
    result = ok("help")
    for name in (
        "task",
        "decide",
        "artifact add",
        "commit",
        "push",
        "view create",
        "help",
    ):
        assert f"madang {name}" in result.output
    assert "--supersedes" in ok("help", "decide").output
    assert "--template" in ok("help", "view", "create").output
    refused("help", "nope", match="알 수 없는 명령")


def test_malformed_state_is_reported(env: Env) -> None:
    (env.page / "ledger.md").write_text("---\nstatus: [\n---\n## 목표\n")
    refused(
        "task", "T1", "--status", "doing", "--title", "x", match="invalid YAML"
    )
