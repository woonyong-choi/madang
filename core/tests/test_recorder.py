import hashlib
import json
from pathlib import Path

import pytest

from madang import recorder
from madang.cli import execute_run
from madang.config import load_config
from madang.recorder.undo import read_log, undo_path
from madang.runners.base import RunResult
from madang.runners.claude import ClaudeStreamParser
from madang.store import frontmatter, pages, projects, summary
from madang.store.home import init_home
from madang.store.log import overview, read_messages

STREAM = ['{"type":"system","subtype":"init"}\n', '{"type":"result"}\n']


class FakeRunner:
    """원본 스트림을 쓰고 정해진 방식으로 페이지를 고치는 러너."""

    name = "claude"

    def __init__(self, act=None, reads=()):
        self.act = act or (lambda cwd, page_dir: None)
        self.reads = list(reads)

    def exec(self, **kw) -> RunResult:
        log: Path = kw["events_log"]
        with log.open("a", encoding="utf-8") as f:
            f.writelines(STREAM)
        self.act(kw["cwd"], log.parent.parent)
        return RunResult(
            status="done", final_text="ANSWER", read_files=self.reads
        )


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


def run(page: Path, home: Path, runner: FakeRunner) -> None:
    execute_run(
        page,
        runner,
        cfg=load_config(home),
        model="m-1",
        effort="medium",
        request="설계해줘",
    )


def body(page: Path) -> str:
    return frontmatter.read(page / "page.md")[1]


def rewrite_status(page: Path, status: str) -> None:
    path = page / "ledger.md"
    header, text = frontmatter.read(path)
    header["status"] = status
    path.write_text(frontmatter.dumps(header, text), encoding="utf-8")


def test_blocks_stack_in_page_md_after_overview(page: Path) -> None:
    pages.update_page(page, lambda h: None, "이력서 개요\n")
    first = recorder.request(page, "요청", None)
    n = recorder.begin(page)
    second = recorder.reply(page, n, "결과")

    text = body(page)
    assert text.startswith("이력서 개요\n\n<!-- b01 | ")
    assert overview(text) == "이력서 개요\n"
    assert [(m.id, m.role, m.text) for m in read_messages(page)] == [
        (first, "user", "요청"),
        (second, "agent", "결과"),
    ]
    assert read_messages(page)[1].attrs == {"run": "1"}
    assert pages.read_header(page / "page.md")["blocks"] == ["b01", "b02"]
    assert summary.page_detail(page, "work")["overview"] == "이력서 개요\n"


def test_run_keeps_raw_stream_and_separate_summary(
    home: Path, page: Path
) -> None:
    run(page, home, FakeRunner())

    assert (page / "runs/1.jsonl").read_text() == "".join(STREAM)
    data = json.loads((page / "runs/1.json").read_text())
    assert data["n"] == 1 and data["events_log"] == "runs/1.jsonl"
    assert not (page / "runs/1.events.jsonl").exists()
    assert "ANSWER" in body(page) and not (page / "log.md").exists()


def test_reads_are_written_to_ledger(
    home: Path, page: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere.txt"
    reads = [str(page / "ledger.md"), "src/app.py", "src/app.py", str(outside)]
    run(page, home, FakeRunner(reads=reads))

    header = pages.read_header(page / "ledger.md")
    assert header["reads"] == ["ledger.md", "repo:src/app.py", str(outside)]


def test_undo_restores_page_files(home: Path, page: Path) -> None:
    (page / "blocks/b02-old.md").write_text("old\n", encoding="utf-8")
    ledger_before = (page / "ledger.md").read_bytes()

    def act(cwd: Path, page_dir: Path) -> None:
        (page_dir / "blocks/b05-new.md").write_text("new\n", encoding="utf-8")
        (page_dir / "blocks/b02-old.md").unlink()
        rewrite_status(page_dir, "doing")

    run(page, home, FakeRunner(act=act))
    recorder.set_status(page, "review", 1)
    assert "ANSWER" in body(page)

    result = recorder.undo(page, 1)

    assert sorted(result.restored) == [
        "blocks/b02-old.md",
        "blocks/b05-new.md",
        "ledger.md",
        "page.md",
    ]
    assert result.skipped == []
    assert (page / "ledger.md").read_bytes() == ledger_before
    assert (page / "blocks/b02-old.md").read_text() == "old\n"
    assert not (page / "blocks/b05-new.md").exists()
    assert "설계해줘" in body(page) and "ANSWER" not in body(page)
    assert pages.read_header(page / "page.md")["blocks"] == ["b03"]
    # 블록 번호는 되감지 않아 되돌린 답의 id를 다시 내주지 않는다.
    assert pages.allocate_block(page) == "b07"
    with pytest.raises(recorder.UndoError, match="already undone"):
        recorder.undo(page, 1)


def test_undo_record_keeps_hashes_and_slots(home: Path, page: Path) -> None:
    run(page, home, FakeRunner(act=lambda cwd, p: rewrite_status(p, "doing")))

    log = read_log(page, 1)
    assert log is not None and undo_path(page, 1).is_file()
    effects = {e.path: e for e in log.effects}
    assert set(effects) == {"ledger.md", "page.md"}
    ledger = effects["ledger.md"]
    assert ledger.kind == "file"
    assert ledger.commit is None and ledger.publish is None
    saved = (page / "runs/objects" / ledger.before).read_bytes()
    assert hashlib.sha256(saved).hexdigest() == ledger.before
    current = (page / "ledger.md").read_bytes()
    assert hashlib.sha256(current).hexdigest() == ledger.after


def test_undo_refuses_files_changed_after_the_run(
    home: Path, page: Path
) -> None:
    run(page, home, FakeRunner(act=lambda cwd, p: rewrite_status(p, "doing")))
    rewrite_status(page, "blocked")

    with pytest.raises(recorder.UndoConflictError) as caught:
        recorder.undo(page, 1)

    assert caught.value.paths == ["ledger.md"]
    assert "ANSWER" in body(page)
    assert read_log(page, 1).undone is None


def test_undo_leaves_project_changes_to_git(home: Path, page: Path) -> None:
    def act(cwd: Path, page_dir: Path) -> None:
        (cwd / "app.py").write_text("print(1)\n", encoding="utf-8")

    run(page, home, FakeRunner(act=act))
    result = recorder.undo(page, 1)

    assert result.skipped == ["repo:app.py"]
    assert (page.parents[2] / "app.py").is_file()


def test_undo_without_record_fails(page: Path) -> None:
    with pytest.raises(recorder.UndoError, match="no undo record"):
        recorder.undo(page, 3)


def test_claude_parser_collects_successful_reads() -> None:
    parser = ClaudeStreamParser()
    calls = [("r1", "/work/a.md", False), ("r2", "/work/b.md", True)]
    for call, path, failed in calls:
        parser.feed(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": call,
                            "name": "Read",
                            "input": {"file_path": path},
                        }
                    ]
                },
            }
        )
        parser.feed(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call,
                            "is_error": failed,
                            "content": "x",
                        }
                    ]
                },
            }
        )
    assert parser.reads == ["/work/a.md"]
