"""메시지 흐름 경로와 이벤트: 실행, 취소, 결정, 미리보기, 미등록 파일."""

import threading
from contextlib import contextmanager
from urllib.parse import quote

from api_support import WS, page_dir, set_status

from madang.store import pages

END = "test.end"
WAIT = 20.0


@contextmanager
def listening(client):
    """``/events``에서 받은 이벤트를 모은다. 블록을 나가면 멈춘다."""
    received: list[dict] = []
    with client.websocket_connect(f"{WS}/events") as ws:

        def pump() -> None:
            while (event := ws.receive_json())["type"] != END:
                received.append(event)

        thread = threading.Thread(target=pump, daemon=True)
        thread.start()
        yield received
        client.app.state.core.hub.publish({"type": END})
        thread.join(WAIT)
        assert not thread.is_alive(), "event stream did not end"


def join(client, page_id: str) -> None:
    client.app.state.core.flows.join(page_id, WAIT)
    assert not client.app.state.core.flows.busy(page_id)


def types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def files(root) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_message_runs_flow_and_streams_events(
    client,
    home,
    page,
    script,
    contract,
) -> None:
    script.acts += [set_status("review"), set_status("review")]
    with listening(client) as events:
        body = contract.check(
            client.post(f"/pages/{page}/messages", json={"text": "구현해줘"}),
            202,
        )
        assert body == {"message": "b01"}
        join(client, page)

    for event in events:
        contract.event(event)
    seen = types(events)
    for name in (
        "run.assembled",
        "run.started",
        "run.progress",
        "run.finished",
        "block.added",
        "page.updated",
    ):
        assert name in seen, name
    assert seen.count("run.finished") == 2
    started = [e for e in events if e["type"] == "run.started"]
    assert [e["run"] for e in started] == [1, 2]
    assert started[0]["data"]["runner"] == "codex"
    added = [e["block"] for e in events if e["type"] == "block.added"]
    assert added[0] == "b01" and len(added) == 3
    finished = next(e for e in events if e["type"] == "run.finished")
    assert finished["data"]["input"]["parts"]["target"] == 0
    assert events[-1]["type"] == "page.updated"
    assert events[-1]["data"]["page"]["status"] == "done"

    detail = contract.check(client.get(f"/pages/{page}"), 200)
    assert detail["status"] == "done"
    assert [r["n"] for r in detail["runs"]] == [1, 2]
    assert detail["blocks"][0]["run"] == 1
    assert "waiting" not in detail
    assert not (home / ".git").exists()

    record = contract.check(client.get(f"/pages/{page}/runs/1"), 200)
    assert record["runner"] == "codex" and record["trigger"]["message"] == "b01"
    contract.check(client.get(f"/pages/{page}/runs/9"), 404)
    stream = contract.check(client.get(f"/pages/{page}/runs/1/events"), 200)
    assert "tool_call" in [e["type"] for e in stream]
    assert stream[-1]["type"] == "done" and stream[-1]["text"]
    contract.check(client.get(f"/pages/{page}/runs/9/events"), 404)


def test_message_validation(client, page, contract) -> None:
    contract.check(
        client.post(f"/pages/{page}/messages", json={"text": "  "}), 400
    )
    contract.check(
        client.post(
            f"/pages/{page}/messages",
            json={"text": "x", "target": {"block": "b09"}},
        ),
        400,
    )
    contract.check(
        client.post("/pages/2026-01-01-none/messages", json={"text": "x"}),
        404,
    )


def test_busy_page_and_cancel(
    client,
    page,
    script,
    contract,
) -> None:
    running = threading.Event()
    release = threading.Event()

    def gate(runner) -> None:
        running.set()
        release.wait(WAIT)

    script.gate = gate
    script.acts.append(set_status("review"))
    with listening(client) as events:
        client.post(f"/pages/{page}/messages", json={"text": "구현해줘"})
        assert running.wait(WAIT)
        busy = client.post(f"/pages/{page}/messages", json={"text": "또"})
        assert contract.check(busy, 409)["error"] == "busy"
        contract.check(client.delete(f"/pages/{page}"), 409)
        contract.check(client.post(f"/pages/{page}/runs/5/cancel"), 404)
        contract.check(client.post(f"/pages/{page}/runs/1/cancel"), 202)
        release.set()
        join(client, page)
        contract.check(client.post(f"/pages/{page}/runs/1/cancel"), 409)

    failed = [e for e in events if e["type"] == "run.failed"]
    assert failed and failed[0]["data"]["result_status"] == "cancelled"
    for event in events:
        contract.event(event)


def test_ambiguous_kind_waits_for_answer(
    client,
    home,
    page,
    script,
    contract,
) -> None:
    with listening(client) as events:
        client.post(f"/pages/{page}/messages", json={"text": "구조를 검토해줘"})
        join(client, page)
    waiting = next(e for e in events if e["type"] == "flow.waiting")
    contract.event(waiting)
    decision = waiting["data"]["decision"]
    assert decision["id"] == "b01"
    assert "design" in decision["question"]["options"]

    detail = contract.check(client.get(f"/pages/{page}"), 200)
    assert detail["waiting"]["decision"]["id"] == "b01"

    answer = f"/pages/{page}/decisions/b01/answer"
    contract.check(client.post(answer, json={"choice": "maybe"}), 400)
    contract.check(
        client.post(
            f"/pages/{page}/decisions/b07/answer", json={"choice": "x"}
        ),
        404,
    )
    script.acts += [set_status("review"), set_status("review")]
    contract.check(client.post(answer, json={"choice": "design"}), 202)
    join(client, page)
    assert script.calls[0]["model"] == "claude-opus-5-5"
    detail = contract.check(client.get(f"/pages/{page}"), 200)
    assert "waiting" not in detail and detail["status"] == "done"


def test_preview_input(client, home, project_root, page, contract) -> None:
    url = f"/pages/{page}/preview-input"
    plain = contract.check(
        client.get(url, params={"text": "로그인 만들어줘"}), 200
    )
    assert plain["kind"] == "build" and plain["runner"] == "codex"
    assert plain["parts"]["target"] == 0
    assert plain["parts"]["ledger"] > 0
    assert not {"root", "project", "state"} & set(plain["parts"])
    assert plain["total_est"] == sum(plain["parts"].values())

    forced = contract.check(
        client.get(url, params={"text": "design: 봐줘"}), 200
    )
    assert forced["kind"] == "design" and forced["model"] == "claude-opus-5-5"

    client.post(
        f"/pages/{page}/blocks",
        json={"type": "doc", "name": "cv", "content": "경력\n" * 50},
    )
    before = files(project_root)
    element = contract.check(
        client.get(
            url,
            params=[
                ("target", "b01"),
                ("elements", "work[1]"),
                ("mode", "edit"),
                ("text", "위로"),
            ],
        ),
        200,
    )
    assert element["kind"] == "small" and element["parts"]["target"] > 0
    contract.check(client.get(url, params={"target": "b09"}), 404)
    # 미리보기는 아무것도 쓰지 않는다
    assert files(project_root) == before


def test_unknown_files_are_reported_and_resolved(
    client,
    home,
    page,
    script,
    contract,
) -> None:
    def leave_three(folder) -> None:
        for name in ("notes.txt", "keep.txt", "junk.txt"):
            (folder / "blocks" / name).write_text("stray\n")
        (folder / "blocks" / ".gitkeep").write_text("")
        set_status("review")(folder)

    script.acts += [leave_three, set_status("review")]
    with listening(client) as events:
        client.post(f"/pages/{page}/messages", json={"text": "구현해줘"})
        join(client, page)
    reported = next(e for e in events if e["type"] == "page.unknown_files")
    contract.event(reported)
    paths = {f["path"] for f in reported["data"]["files"]}
    assert "blocks/notes.txt" in paths

    url = f"/pages/{page}/unknown-files"
    listed = contract.check(client.get(url), 200)
    assert {f["path"] for f in listed} == {
        "blocks/notes.txt",
        "blocks/keep.txt",
        "blocks/junk.txt",
    }
    assert contract.check(client.get(f"/pages/{page}"), 200)["unknown_files"]

    def resolve(path: str, action: str):
        return client.post(
            f"{url}/{quote(path, safe='')}", json={"action": action}
        )

    left = contract.check(resolve("blocks/notes.txt", "artifact"), 200)
    assert len(left) == 2
    folder = page_dir(home, page)
    state = pages.read_header(folder / "ledger.md")
    assert "blocks/notes.txt" in state["artifacts"]
    contract.check(resolve("blocks/keep.txt", "keep"), 200)
    assert contract.check(resolve("blocks/junk.txt", "delete"), 200) == []
    assert not (folder / "blocks/junk.txt").exists()
    assert (folder / "blocks/keep.txt").exists()
    contract.check(resolve("blocks/junk.txt", "delete"), 404)
    contract.check(resolve("../../secrets.yaml", "delete"), 404)
    contract.check(resolve("blocks/keep.txt", "burn"), 400)
