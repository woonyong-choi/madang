"""보내기 한 번의 흐름: 실행 → 기록 → 정책(머지·게시) → 기록 → 되돌리기."""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from madang import cli, git, recorder
from madang.config import load_config
from madang.graph import Flow
from madang.recorder import published
from madang.recorder.undo import read_log
from madang.runners.base import RunResult, Usage
from madang.store import frontmatter, pages, projects
from madang.store.home import init_home
from madang.store.log import read_messages
from madang.validate import validate_ledger

Act = Callable[[Path, Path], None]


class Script:
    """러너 호출 순서대로 에이전트 동작을 내준다. 모든 호출을 기록한다."""

    def __init__(self, *acts: Act) -> None:
        self.acts = list(acts)
        self.calls: list[dict] = []

    def runner(self, name: str, cfg) -> "FakeRunner":
        return FakeRunner(name, self)


class FakeRunner:
    """작업 폴더와 페이지 폴더를 받아 에이전트 동작 하나를 흉내 낸다."""

    def __init__(self, name: str, script: Script) -> None:
        self.name = name
        self.script = script

    def exec(self, **kw) -> RunResult:
        page_dir = kw["events_log"].parent.parent
        self.script.calls.append({**kw, "name": self.name})
        self.script.acts.pop(0)(kw["cwd"], page_dir)
        return RunResult(
            status="done",
            usage=Usage(input=100, cached=10, output=5),
            final_text=f"ANSWER-{len(self.script.calls)}",
            duration=0.1,
        )

    def cancel(self) -> None:
        pass


def review(cwd: Path, page_dir: Path) -> None:
    """구현을 마쳤다고 ledger.md status를 review로 쓴다."""
    ledger = page_dir / "ledger.md"
    header, body = frontmatter.read(ledger)
    header["status"] = "review"
    ledger.write_text(frontmatter.dumps(header, body))


def write(name: str, text: str) -> Act:
    """작업 폴더에 파일을 쓰고 review로 넘기는 에이전트 동작."""

    def act(cwd: Path, page_dir: Path) -> None:
        path = cwd / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        review(cwd, page_dir)

    return act


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("MADANG_BY", raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    init_home(root)
    return root


def project_config(root: Path, **settings) -> None:
    (root / ".madang" / "config.yaml").write_text(
        yaml.safe_dump(settings, allow_unicode=True)
    )


@pytest.fixture
def doc_page(home: Path, tmp_path: Path) -> Path:
    """자동 게시가 켜진 문서 프로젝트(git 아님)의 페이지."""
    root = tmp_path / "notes"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "guide.md").write_text("# 안내\n\n처음\n")
    project = projects.add(home, root, project_id="notes")
    project_config(
        root,
        policy={"auto_publish": True},
        publish={"include": ["docs"], "target": "folder:site"},
    )
    return pages.create_page(project.pages_dir, "안내서", slug="guide")


def code_project(home: Path, tmp_path: Path, test: str | None) -> Path:
    """git 저장소 프로젝트의 코딩 페이지. ``test``는 선언된 테스트 명령."""
    root = tmp_path / "work"
    root.mkdir()
    git.run(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text("v = 1\n")
    git.stage(root)
    git.commit(root, "init")
    project = projects.add(home, root, project_id="work")
    project_config(root, policy={"auto_merge": {"test": test}})
    page_dir = pages.create_page(project.pages_dir, "잠금", slug="lock")
    header, body = frontmatter.read(page_dir / "page.md")
    header["kind"] = "code"
    (page_dir / "page.md").write_text(frontmatter.dumps(header, body))
    return page_dir


def flow(home: Path, script: Script, seen: list | None = None) -> Flow:
    def on_event(name: str, payload: dict) -> None:
        if seen is not None:
            seen.append((name, payload))

    return Flow(load_config(home), runners=script.runner, on_event=on_event)


def ledger_status(page_dir: Path) -> str:
    return pages.read_header(page_dir / "ledger.md")["status"]


# 문서 페이지 → 게시


def test_doc_page_publishes_changed_documents(
    home: Path, doc_page: Path
) -> None:
    root = doc_page.parents[2]
    script = Script(write("docs/guide.md", "# 안내\n\n고침\n"), review)
    seen: list = []

    result = flow(home, script, seen).start(doc_page.name, "안내서를 고쳐줘")

    assert result.waiting is None
    assert result.state["result_status"] == "done"
    assert ledger_status(doc_page) == "done"
    assert (root / "site" / "docs" / "guide.html").is_file()
    record = published.latest(root)
    assert record is not None and record.documents == ["docs/guide.md"]
    n = result.state["run_n"]
    effects = read_log(doc_page, n).effects
    assert [(e.kind, e.publish) for e in effects if e.kind == "publish"] == [
        ("publish", record.n)
    ]
    settled = [p for name, p in seen if name == "flow.settled"]
    assert settled == [
        {
            "page": doc_page.name,
            "message": result.thread_id.rsplit("/", 1)[-1],
            "n": n,
            "merged": None,
            "published": record.n,
            "push_error": None,
        }
    ]


def test_doc_page_without_document_change_does_not_publish(
    home: Path, doc_page: Path
) -> None:
    script = Script(review, review)

    result = flow(home, script).start(doc_page.name, "검토만 해줘")

    assert result.state["result_status"] == "done"
    assert published.latest(doc_page.parents[2]) is None


# 코드 페이지 → 테스트 → 머지


def test_code_page_merges_after_tests_pass(home: Path, tmp_path: Path) -> None:
    page_dir = code_project(home, tmp_path, test="test -f lock.py")
    root = page_dir.parents[2]
    worktree = root.parent / "work.wt" / page_dir.name
    script = Script(write("lock.py", "locked = True\n"), review)

    result = flow(home, script).start(page_dir.name, "잠금을 넣어줘")

    assert result.waiting is None
    assert result.state["result_status"] == "done"
    assert script.calls[0]["cwd"] == worktree
    assert (root / "lock.py").read_text() == "locked = True\n"
    assert not worktree.exists()
    assert not git.has_branch(root, f"page/{page_dir.name}")
    assert git.status(root) == {}
    log = read_log(page_dir, result.state["run_n"])
    merges = [e for e in log.effects if e.kind == "merge"]
    assert len(merges) == 1 and merges[0].commit == git.rev_parse(root)
    # 머지가 지운 워크트리의 커밋은 머지를 되돌리면 함께 되감긴다.
    assert not [e for e in log.effects if e.kind == "commit"]


def test_prompt_forbids_direct_side_effects(home: Path, doc_page: Path) -> None:
    script = Script(review, review)

    flow(home, script).start(doc_page.name, "검토만 해줘")

    prompt = script.calls[0]["prompt"]
    assert "git 명령" in prompt and "직접 실행하지 않는다" in prompt
    assert "madang runs add" in prompt


# 테스트 실패 → 묻는 블록 → 답 → 재개


def test_failed_tests_ask_on_page_then_retry_resumes(
    home: Path, tmp_path: Path
) -> None:
    page_dir = code_project(home, tmp_path, test="test -f ok.txt")
    root = page_dir.parents[2]
    script = Script(
        write("lock.py", "locked = True\n"),
        review,
        write("ok.txt", "ok\n"),
        review,
    )
    loop = flow(home, script)

    stopped = loop.start(page_dir.name, "잠금을 넣어줘")

    assert stopped.waiting is not None
    assert stopped.waiting["reason"] == "policy"
    assert stopped.waiting["options"] == ["merge", "retry", "stop"]
    ask = read_messages(page_dir)[-1]
    assert ask.role == "router" and ask.attrs["ask"] == "true"
    assert ask.attrs["options"] == "merge,retry,stop"
    assert "테스트 실패(종료 코드 1)" in ask.text
    assert "선택지: merge | retry | stop" in ask.text
    assert not (root / "lock.py").exists()
    assert loop.waiting_on(page_dir.name) == [
        (stopped.thread_id, stopped.waiting)
    ]

    result = loop.resume(stopped.thread_id, "retry")

    assert result.waiting is None
    assert result.state["result_status"] == "done"
    retry_prompt = script.calls[2]["prompt"]
    assert "정책이 머지·게시를 멈췄다" in retry_prompt
    assert "테스트 실패(종료 코드 1)" in retry_prompt
    assert (root / "lock.py").is_file() and (root / "ok.txt").is_file()
    answer = next(m for m in read_messages(page_dir) if "answer" in m.attrs)
    assert (answer.role, answer.text) == ("user", "retry")
    assert answer.attrs["answer"] == ask.id


def test_missing_test_command_asks_and_approval_merges(
    home: Path, tmp_path: Path
) -> None:
    page_dir = code_project(home, tmp_path, test=None)
    root = page_dir.parents[2]
    loop = flow(home, Script(write("lock.py", "x = 1\n"), review))

    stopped = loop.start(page_dir.name, "잠금을 넣어줘")

    assert stopped.waiting is not None
    assert "테스트 명령 없음" in read_messages(page_dir)[-1].text
    result = loop.resume(stopped.thread_id, "merge")

    assert result.waiting is None and result.state["result_status"] == "done"
    assert (root / "lock.py").is_file()


def test_conflict_cannot_be_approved(home: Path, tmp_path: Path) -> None:
    page_dir = code_project(home, tmp_path, test="true")
    root = page_dir.parents[2]

    def clash(cwd: Path, page_dir: Path) -> None:
        (cwd / "app.py").write_text("v = 'page'\n")
        (root / "app.py").write_text("v = 'main'\n")
        git.stage(root)
        git.commit(root, "edit on main")
        review(cwd, page_dir)

    loop = flow(home, Script(clash, review))

    stopped = loop.start(page_dir.name, "값을 바꿔줘")

    assert stopped.waiting is not None
    assert stopped.waiting["options"] == ["retry", "again", "stop"]
    assert "충돌: app.py" in read_messages(page_dir)[-1].text
    result = loop.resume(stopped.thread_id, "stop")
    assert result.waiting is None
    assert (root / "app.py").read_text() == "v = 'main'\n"


# 되돌리기


def test_undo_reverts_merge_and_page_files(home: Path, tmp_path: Path) -> None:
    page_dir = code_project(home, tmp_path, test="test -f lock.py")
    root = page_dir.parents[2]
    script = Script(write("lock.py", "locked = True\n"), review)
    result = flow(home, script).start(page_dir.name, "잠금을 넣어줘")
    n = result.state["run_n"]
    merge = git.rev_parse(root)

    undone = recorder.undo(page_dir, n)

    assert not (root / "lock.py").exists()
    assert git.log(root)[0].subject.startswith("Revert")
    assert git.is_ancestor(root, merge)  # 이력은 지우지 않는다
    assert undone.reverted == [git.rev_parse(root)]
    assert "ledger.md" in undone.restored
    assert ledger_status(page_dir) == "review"
    assert all(m.attrs.get("run") != str(n) for m in read_messages(page_dir))


def test_undo_command_unpublishes_and_restores(
    home: Path, doc_page: Path
) -> None:
    root = doc_page.parents[2]
    script = Script(write("docs/guide.md", "# 안내\n\n고침\n"), review)
    result = flow(home, script).start(doc_page.name, "안내서를 고쳐줘")
    n = result.state["run_n"]
    assert (root / "site").is_dir()

    out = CliRunner().invoke(
        cli.app, ["undo", doc_page.name, str(n), "--home", str(home)]
    )

    assert out.exit_code == 0, out.output
    assert f"undid run {n}" in out.output and "unpublished 1" in out.output
    # 게시 모듈은 대상 폴더를 게시 전 파일 상태로 되돌린다(빈 폴더는 남는다).
    assert not any((root / "site").iterdir())
    assert published.read(root, 1).undone is not None
    assert ledger_status(doc_page) == "review"
    again = CliRunner().invoke(
        cli.app, ["undo", doc_page.name, str(n), "--home", str(home)]
    )
    assert again.exit_code == 1 and "already undone" in again.output


def test_undo_refuses_publish_superseded_by_later_one(
    home: Path, doc_page: Path
) -> None:
    root = doc_page.parents[2]
    loop = flow(
        home,
        Script(
            write("docs/guide.md", "# 안내\n\n하나\n"),
            review,
            write("docs/guide.md", "# 안내\n\n둘\n"),
            review,
        ),
    )
    first = loop.start(doc_page.name, "하나로 고쳐줘")
    loop.start(doc_page.name, "둘로 고쳐줘")

    with pytest.raises(recorder.UndoConflictError) as caught:
        recorder.undo(doc_page, first.state["run_n"])

    assert f"{root}#publish-1" in caught.value.paths
    assert published.read(root, 1).undone is None


# Ledger 검사기: 실행물 선언 대조


def runnable_ledger(page_dir: Path, name: str, command: str) -> Path:
    ledger = page_dir / "ledger.md"
    header, body = frontmatter.read(ledger)
    header["artifacts"] = [
        {
            "path": "repo:serve.sh",
            "run": True,
            "name": name,
            "command": command,
        }
    ]
    ledger.write_text(frontmatter.dumps(header, body))
    return ledger


def test_runnable_artifact_must_match_declared_run(
    home: Path, doc_page: Path
) -> None:
    root = doc_page.parents[2]
    (root / "serve.sh").write_text("echo hi\n")
    ledger = runnable_ledger(doc_page, "서버", "sh serve.sh")

    issues = validate_ledger(ledger, repo=root)
    assert [i.code for i in issues] == ["run-undeclared"]

    project_config(root, runs=[{"name": "서버", "command": "sh serve.sh"}])
    assert validate_ledger(ledger, repo=root) == []

    runnable_ledger(doc_page, "서버", "bash serve.sh")
    assert [i.code for i in validate_ledger(ledger, repo=root)] == [
        "run-undeclared"
    ]


def test_runnable_artifact_needs_name_and_command(
    home: Path, doc_page: Path
) -> None:
    root = doc_page.parents[2]
    (root / "serve.sh").write_text("echo hi\n")
    ledger = doc_page / "ledger.md"
    header, body = frontmatter.read(ledger)
    header["artifacts"] = [{"path": "repo:serve.sh", "run": True}]
    ledger.write_text(frontmatter.dumps(header, body))

    issues = validate_ledger(ledger, repo=root)

    assert [i.code for i in issues] == ["invalid-value"]
