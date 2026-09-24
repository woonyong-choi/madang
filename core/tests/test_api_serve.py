"""``madang serve``: 127.0.0.1 바인딩, 포트 증가, core.port 기록과 삭제."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from madang.api.server import LOOPBACK, bind_socket

WAIT = 20.0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOOPBACK, 0))
        return sock.getsockname()[1]


def test_bind_socket_skips_ports_in_use() -> None:
    taken = socket.socket()
    taken.bind((LOOPBACK, 0))
    port = taken.getsockname()[1]
    try:
        sock = bind_socket(port, attempts=5)
        try:
            host, chosen = sock.getsockname()
            assert host == LOOPBACK and chosen != port
        finally:
            sock.close()
    finally:
        taken.close()


@pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
def test_serve_writes_and_removes_port_file(
    tmp_path: Path, stop: signal.Signals
) -> None:
    home = tmp_path / "home"
    taken = socket.socket()
    taken.bind((LOOPBACK, free_port()))
    taken.listen()
    start = taken.getsockname()[1]
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "madang.cli",
            "serve",
            "--home",
            str(home),
            "--port",
            str(start),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        port_file = home / "core.port"
        deadline = time.monotonic() + WAIT
        port = None
        while time.monotonic() < deadline:
            if port_file.is_file() and port_file.read_text().strip():
                port = int(port_file.read_text())
                try:
                    health = httpx.get(f"http://{LOOPBACK}:{port}/health")
                    break
                except httpx.ConnectError:
                    pass
            assert proc.poll() is None, proc.stdout.read()
            time.sleep(0.1)
        assert port is not None and port > start
        assert health.json()["status"] == "ok"
        status = httpx.get(f"http://{LOOPBACK}:{port}/home").json()
        assert status["initialized"] is False
    finally:
        proc.send_signal(stop)
        proc.wait(WAIT)
        taken.close()
    assert proc.returncode == 0, proc.stdout.read()
    assert not port_file.exists()
