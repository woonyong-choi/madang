"""실행 대상 경로: 선언, core 소유 실행, 관찰한 포트와 그 선언."""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from api_support import PROJECT

from madang import runs

BASE = f"/projects/{PROJECT}"
WAIT = 20.0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve_command(port: int) -> str:
    return f"{sys.executable} -m http.server {port} --bind 127.0.0.1"


def until(check, timeout: float = WAIT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.1)
    raise AssertionError("timed out")


@pytest.fixture
def events(client, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []
    monkeypatch.setattr(client.app.state.core.hub, "publish", seen.append)
    return seen


@pytest.fixture
def supervisor(client):
    yield client.app.state.core.supervisor
    client.app.state.core.supervisor.stop_all()


def test_declare_list_and_refusals(
    client, project_root: Path, contract
) -> None:
    (project_root / "site").mkdir()
    made = contract.check(
        client.post(
            f"{BASE}/runs",
            json={"name": "사이트", "command": "echo hi", "cwd": "site"},
        ),
        201,
    )
    assert made == {
        "name": "사이트",
        "command": "echo hi",
        "cwd": "site",
        "running": False,
        "ports": [],
    }
    listed = contract.check(client.get(f"{BASE}/runs"), 200)
    assert [t["name"] for t in listed] == ["사이트"]
    assert runs.find(project_root, "사이트").cwd == "site"

    dup = client.post(f"{BASE}/runs", json={"name": "사이트", "command": "x"})
    assert "already declared" in contract.check(dup, 400)["message"]
    out = client.post(
        f"{BASE}/runs", json={"name": "a", "command": "x", "cwd": "../x"}
    )
    contract.check(out, 400)
    contract.check(client.post(f"{BASE}/runs/nope/start"), 404)
    stop = client.post(f"{BASE}/runs/%EC%82%AC%EC%9D%B4%ED%8A%B8/stop")
    assert "not running" in contract.check(stop, 409)["message"]


def test_start_is_denied_by_policy(
    client, project_root: Path, supervisor, contract
) -> None:
    runs.declare(project_root, "danger", "git push --force origin main")
    denied = contract.check(client.post(f"{BASE}/runs/danger/start"), 409)
    assert denied["error"] == "denied"
    assert supervisor.running() == []


def test_start_opens_logs_ports_and_stop(
    client, project_root: Path, supervisor, events, contract
) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    runs.declare(project_root, "web", serve_command(port), opens=url)

    started = contract.check(client.post(f"{BASE}/runs/web/start"), 200)
    assert started["running"] is True and started["pid"] > 0
    contract.check(client.post(f"{BASE}/runs/web/start"), 409)
    opened = until(lambda: [e for e in events if e["type"] == "runs.opened"])
    assert opened[0]["data"] == {"name": "web", "url": url}
    changed = [e for e in events if e["type"] == "ports.changed"]
    assert port in [p["port"] for p in changed[0]["data"]["ports"]]

    ports = contract.check(client.get(f"{BASE}/ports"), 200)
    mine = next(p for p in ports if p["port"] == port)
    assert mine["run"] == "web" and mine["cwd"] == "."
    status = contract.check(client.get(f"{BASE}/runs"), 200)[0]
    assert port in [p["port"] for p in status["ports"]]

    stopped = contract.check(client.post(f"{BASE}/runs/web/stop"), 200)
    assert stopped["running"] is False
    until(lambda: [e for e in events if e["data"].get("exit_code") is not None])
    for event in events:
        contract.event(event)


def test_observed_port_is_declared_from_the_process(
    client, project_root: Path, contract
) -> None:
    port = free_port()
    (project_root / "public").mkdir()
    proc = subprocess.Popen(
        serve_command(port).split(),
        cwd=project_root / "public",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        seen = until(
            lambda: [
                p
                for p in contract.check(client.get(f"{BASE}/ports"), 200)
                if p["port"] == port
            ]
        )
        assert seen[0]["cwd"] == "public" and "run" not in seen[0]
        made = contract.check(
            client.post(f"{BASE}/ports/{port}/declare", json={"name": "미리"}),
            201,
        )
    finally:
        proc.terminate()
        proc.wait(10)
    assert made["cwd"] == "public"
    assert "http.server" in made["command"]
    assert made["opens"] == f"http://localhost:{port}"
    assert runs.find(project_root, "미리").opens == made["opens"]
    gone = client.post(f"{BASE}/ports/{port}/declare", json={"name": "x"})
    contract.check(gone, 404)
