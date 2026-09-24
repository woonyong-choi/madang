"""``madang serve``: 127.0.0.1에만 묶어 core API를 띄운다.

포트가 쓰이고 있으면 다음 포트를 시도한다. 고른 포트는
``<home>/core.port``에 적고 끝날 때 지운다.
"""

from __future__ import annotations

import logging
import signal
import socket
from pathlib import Path
from types import FrameType

import uvicorn

from madang import viewers
from madang.api.app import create_app
from madang.api.routes.viewers import announce_viewer

LOOPBACK = "127.0.0.1"
PORT_ATTEMPTS = 50

log = logging.getLogger(__name__)


def bind_socket(port: int, attempts: int = PORT_ATTEMPTS) -> socket.socket:
    """``port``부터 차례로 127.0.0.1에 묶어 본다.

    Args:
        port: 처음 시도할 포트.
        attempts: 시도할 포트 수.

    Returns:
        묶은(아직 listen하지 않은) 소켓.

    Raises:
        OSError: 모든 포트가 쓰이고 있다.
    """
    last: OSError | None = None
    for candidate in range(port, port + attempts):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((LOOPBACK, candidate))
        except OSError as exc:
            sock.close()
            last = exc
            continue
        return sock
    raise OSError(
        f"no free port in {port}..{port + attempts - 1} on {LOOPBACK}"
    ) from last


class _TerminatedError(Exception):
    """SIGTERM으로 멈췄다."""


def _stop(signum: int, frame: FrameType | None) -> None:
    raise _TerminatedError


def serve(home: Path, port: int) -> None:
    """Core API를 띄우고 멈출 때까지 블록한다.

    Args:
        home: 앱 홈. 아직 초기화되지 않았어도 된다.
        port: 처음 시도할 포트.

    Raises:
        OSError: 쓸 수 있는 포트가 없다.
    """
    sock = bind_socket(port)
    chosen = sock.getsockname()[1]
    app = create_app(home, core_url=f"http://{LOOPBACK}:{chosen}")
    core = app.state.core
    core.port = chosen
    core.write_port()
    registry = viewers.Registry(core.home)
    watcher = viewers.ViewerWatcher(
        registry,
        lambda name: announce_viewer(
            core, name, registry.status(registry.get(name))
        ),
    )
    watcher.start()
    log.info("madang core on http://%s:%d (home %s)", LOOPBACK, chosen, home)
    server = uvicorn.Server(uvicorn.Config(app, log_level="info"))
    # uvicorn은 멈춘 뒤 받은 신호를 원래 처리기로 다시 올린다. 기본 SIGTERM
    # 처리기는 정리 없이 프로세스를 끝내므로 예외로 바꿔 아래에서 정리한다.
    previous = signal.signal(signal.SIGTERM, _stop)
    try:
        server.run(sockets=[sock])
    except (KeyboardInterrupt, _TerminatedError):
        log.info("madang core stopped")
    finally:
        signal.signal(signal.SIGTERM, previous)
        watcher.stop()
        core.flows.shutdown()
        core.supervisor.stop_all()
        core.remove_port()
        sock.close()
