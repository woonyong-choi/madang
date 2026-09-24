import json
from pathlib import Path

import pytest
from conftest import STREAMS

from madang.config import RunnerSpec, load_config
from madang.runners import ClaudeRunner, CodexRunner
from madang.runners.record import run_page, timeout_seconds
from madang.store import runs
from madang.store.page import latest_run


@pytest.fixture
def page_dir(tmp_path: Path) -> Path:
    page = tmp_path / "work" / ".madang" / "pages" / "2026-09-24-demo"
    page.mkdir(parents=True)
    return page


def test_allocate_increments(page_dir: Path) -> None:
    assert runs.allocate(page_dir) == 1
    assert runs.allocate(page_dir) == 2
    assert runs.events_path(page_dir, 2).is_file()
    assert (page_dir / "runs" / ".last").read_text().strip() == "2"


def test_allocate_never_reuses(page_dir: Path) -> None:
    for _ in range(3):
        runs.allocate(page_dir)
    for n in (2, 3):
        runs.events_path(page_dir, n).unlink()
    assert runs.allocate(page_dir) == 4


def test_allocate_continues_after_existing_records(page_dir: Path) -> None:
    (page_dir / "runs").mkdir()
    (page_dir / "runs" / "7.json").write_text("{}")
    assert runs.allocate(page_dir) == 8


def test_write_and_read(page_dir: Path) -> None:
    record = runs.RunRecord(
        n=1,
        kind="small",
        tier=1,
        runner="codex",
        model="gpt-6-luna",
        effort="high",
        usage=runs.RunUsage(input=29104, cached=24310, output=612),
        changed_files=["blocks/b03.json"],
        result_status="done",
        verify=runs.RunVerify(cmd="pytest", ok=True),
        events_log=runs.events_rel(1),
        custom="kept",
    )
    path = runs.write_run(page_dir, record)
    data = json.loads(path.read_text())
    assert data["usage"] == {"input": 29104, "cached": 24310, "output": 612}
    assert data["verify"] == {"cmd": "pytest", "ok": True}
    assert data["events_log"] == "runs/1.jsonl"
    assert data["custom"] == "kept"
    assert runs.read_run(page_dir, 1) == record
    assert runs.list_runs(page_dir) == [1]
    # 검증기의 run 조회로 읽을 수 있다
    assert latest_run(page_dir)[1]["n"] == 1
    assert not list((page_dir / "runs").glob("*.tmp"))


def test_read_invalid_json(page_dir: Path) -> None:
    (page_dir / "runs").mkdir()
    (page_dir / "runs" / "1.json").write_text("{")
    with pytest.raises(ValueError, match="invalid JSON"):
        runs.read_run(page_dir, 1)


def test_timeout_by_kind(tmp_path: Path) -> None:
    config = load_config(tmp_path / "home")
    assert timeout_seconds(config, "small") == 300
    assert timeout_seconds(config, "design") == 1800
    assert timeout_seconds(config, "unknown") is None


def test_run_page_records(
    page_dir: Path, fake_spec: RunnerSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = page_dir.parents[3]
    config = load_config(home)
    monkeypatch.setenv("FAKE_STREAM", str(STREAMS / "codex-tools.jsonl"))
    runner = CodexRunner(fake_spec, home=home)
    seen = []

    run = run_page(
        runner,
        config=config,
        page_dir=page_dir,
        cwd=page_dir,
        prompt="p",
        model="gpt-6-luna",
        effort="high",
        kind="small",
        tier=1,
        trigger={"message": "b06", "mode": "edit"},
        on_event=seen.append,
    )

    assert run.n == 1
    assert run.result.status == "done"
    assert seen == run.result.events
    record = runs.read_run(page_dir, 1)
    assert (
        record.runner == "codex" and record.kind == "small" and record.tier == 1
    )
    assert record.usage == runs.RunUsage(input=15230, cached=11904, output=402)
    assert record.result_status == "done"
    assert record.events_log == "runs/1.jsonl"
    assert record.trigger == {"message": "b06", "mode": "edit"}
    assert record.started <= record.finished
    assert record.changed_files == [
        "/work/project/hello.txt",
        "/work/project/README.md",
    ]
    assert (
        runs.events_path(page_dir, 1).read_text()
        == (STREAMS / "codex-tools.jsonl").read_text()
    )

    assert (
        run_page(
            runner,
            config=config,
            page_dir=page_dir,
            cwd=page_dir,
            prompt="p",
            model="m",
            effort="low",
            kind="small",
        ).n
        == 2
    )


def test_changed_files_relative_to_page(
    page_dir: Path,
    tmp_path: Path,
    fake_spec: RunnerSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = tmp_path / "s.jsonl"
    target = page_dir / "blocks" / "b03.json"
    stream.write_text(
        "\n".join(
            json.dumps(o)
            for o in [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "t",
                                "name": "Write",
                                "input": {"file_path": str(target)},
                            }
                        ]
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "t",
                                "content": "ok",
                            }
                        ]
                    },
                },
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "ok",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("FAKE_STREAM", str(stream))
    home = page_dir.parents[3]
    run = run_page(
        ClaudeRunner(fake_spec, home=home),
        config=load_config(home),
        page_dir=page_dir,
        cwd=tmp_path,
        prompt="p",
        model="m",
        effort="low",
        kind="small",
    )
    assert run.record.changed_files == ["blocks/b03.json"]


def test_latest_run_picks_highest_numbered_record(page_dir: Path) -> None:
    assert latest_run(page_dir) is None
    runs_dir = page_dir / "runs"
    runs_dir.mkdir()
    for n in (2, 10):
        (runs_dir / f"{n}.json").write_text(json.dumps({"n": n}))
    (runs_dir / "11.jsonl").write_text("")
    (runs_dir / ".last").write_text("11\n")
    path, data = latest_run(page_dir)
    assert path.name == "10.json" and data == {"n": 10}
    (runs_dir / "12.json").write_text("[1]")
    with pytest.raises(ValueError, match="JSON object"):
        latest_run(page_dir)


def test_atomic_write_keeps_newlines(tmp_path: Path) -> None:
    from madang.store.files import atomic_write

    target = tmp_path / "a.txt"
    atomic_write(target, "one\r\ntwo\n")
    assert target.read_bytes() == b"one\r\ntwo\n"
    assert list(tmp_path.iterdir()) == [target]
