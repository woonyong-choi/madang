"""시스템·설정 경로: 상태, 러너, 앱 홈, 라우팅 표, 오류 형태."""

from pathlib import Path

import pytest
from api_support import LOCAL, WS, subjects
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from madang.api.app import create_app


def test_health(client, contract) -> None:
    body = contract.check(client.get("/health"), 200)
    assert body["status"] == "ok"


def test_runners_are_cached_and_hide_tool_output(home, contract) -> None:
    calls: list[str] = []

    def probe(name, spec):
        calls.append(name)
        return None if name == "claude" else "not logged in"

    app = create_app(home, probe=probe)
    with TestClient(app, base_url=LOCAL) as test_client:
        body = contract.check(test_client.get("/runners"), 200)
        contract.check(test_client.get("/runners"), 200)
    assert calls == ["claude", "codex"]
    assert body["runners"] == [
        {"name": "claude", "available": True, "auth": "subscription"},
        {
            "name": "codex",
            "available": False,
            "auth": "subscription",
            "reason": "not logged in",
        },
    ]


def test_uninitialized_home_then_init(tmp_path: Path, contract) -> None:
    first = tmp_path / "first"
    app = create_app(first, probe=lambda n, s: None)
    core = app.state.core
    core.port = 7471
    core.write_port()
    with TestClient(app, base_url=LOCAL) as test_client:
        status = contract.check(test_client.get("/home"), 200)
        assert status == {"path": str(first.resolve()), "initialized": False}
        assert contract.check(test_client.get("/spaces"), 200) == []
        contract.check(test_client.get("/pages/2026-09-24-x"), 404)
        failed = test_client.post("/spaces", json={"slug": "a", "title": "a"})
        assert contract.check(failed, 409)["error"] == "conflict"
        contract.check(test_client.get("/config/routes"), 409)
        contract.check(test_client.get("/runners"), 200)

        target = tmp_path / "chosen"
        remote = "git@github.com:me/madang-home.git"
        body = contract.check(
            test_client.post(
                "/home", json={"path": str(target), "remote": remote}
            ),
            200,
        )
        assert body == {
            "path": str(target.resolve()),
            "initialized": True,
            "remote": remote,
        }
        spaces = contract.check(test_client.get("/spaces"), 200)
        assert [s["slug"] for s in spaces] == ["root"]
        # 다시 해도 덮어쓰지 않는다
        contract.check(
            test_client.post("/home", json={"path": str(target)}), 200
        )
    assert (target / "core.port").read_text().strip() == "7471"
    assert not (first / "core.port").exists()
    assert subjects(target)[0] == "[home] set remote"
    assert "home_remote: " in (target / "config/madang.yaml").read_text()


def test_init_refuses_foreign_folder(client, tmp_path, contract) -> None:
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("mine\n")
    response = client.post("/home", json={"path": str(foreign)})
    assert contract.check(response, 409)["error"] == "conflict"
    bad = client.post("/home", json={"path": str(foreign), "remote": "a b"})
    assert contract.check(bad, 400)["error"] == "invalid"


def test_routes_document_round_trip(client, home, contract) -> None:
    body = contract.check(client.get("/config/routes"), 200)
    assert body["text"] == (home / "config/routes.yaml").read_text()

    text = body["text"].replace("default_kind: build", "default_kind: small")
    saved = contract.check(
        client.put("/config/routes", json={"text": text}), 200
    )
    assert saved["text"] == text
    assert (home / "config/routes.yaml").read_text() == text
    assert subjects(home)[0] == "[home] edit config/routes.yaml"


def test_routes_document_is_validated(client, home, contract) -> None:
    original = (home / "config/routes.yaml").read_text()
    cases = {
        "kinds: [a\n": "invalid-yaml",
        "kinds: [build]\n": "missing-key",
        "kinds: [build]\ndefault_kind: design\ntiers: {}\n": "invalid-value",
        "kinds: [build]\ndefault_kind: build\n"
        "tiers: {build: [{runner: gemini, model: x}]}\n": "invalid-value",
        "kinds: nope\ndefault_kind: build\ntiers: {}\n": "invalid-value",
    }
    for text, code in cases.items():
        response = client.put("/config/routes", json={"text": text})
        body = contract.check(response, 400)
        assert body["issues"][0]["code"] == code, text
        assert body["issues"][0]["path"] == "config/routes.yaml"
    assert (home / "config/routes.yaml").read_text() == original
    runner = client.put(
        "/config/routes",
        json={
            "text": "kinds: [build]\ndefault_kind: build\n"
            "tiers: {build: [{runner: gemini, model: x}]}\n"
        },
    ).json()
    assert runner["issues"][0]["line"] == 3


def test_errors_use_contract_shapes(client, contract) -> None:
    missing = client.get("/pages/2026-09-30-missing")
    assert contract.check(missing, 404)["error"] == "not_found"
    bad = client.post("/spaces", json={"slug": "x"})
    body = contract.check(bad, 400)
    assert body["issues"][0]["code"] == "invalid-value"
    unknown = client.post("/spaces", json={"slug": "x", "title": "x", "z": 1})
    contract.check(unknown, 400)
    nowhere = client.get("/nowhere")
    assert nowhere.status_code == 404
    assert nowhere.json()["error"] == "not_found"


def test_only_local_clients_are_served(home) -> None:
    app = create_app(home, probe=lambda n, s: None)
    with TestClient(app, base_url="http://evil.example") as remote:
        assert remote.get("/health").status_code == 403
    with TestClient(app, base_url=LOCAL) as local:
        assert local.get("/health").status_code == 200
        foreign = {"origin": "https://evil.example"}
        assert local.get("/health", headers=foreign).status_code == 403
        same = {"origin": "http://localhost:5173"}
        assert local.get("/health", headers=same).status_code == 200
        with local.websocket_connect(f"{WS}/events") as ws:
            client_hub = app.state.core.hub
            client_hub.emit("memory.updated", {"layer": "root", "tokens": 1})
            assert ws.receive_json()["type"] == "memory.updated"
        with (
            pytest.raises(WebSocketDisconnect),
            local.websocket_connect(f"{WS}/events", headers=foreign) as ws,
        ):
            ws.receive_json()
