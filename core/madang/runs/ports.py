"""포트 관찰: 프로세스 트리가 실제로 LISTEN 중인 포트."""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True, order=True)
class Listen:
    """열린 포트 하나(관찰 사실).

    Attributes:
        port: 포트 번호.
        host: 대기 주소.
        pid: 포트를 연 프로세스.
    """

    port: int
    host: str
    pid: int


def listening_ports(pid: int) -> list[Listen]:
    """``pid``와 그 자손이 LISTEN 중인 TCP 포트를 포트 순으로 반환한다.

    짐작하지 않는다. 운영체제가 보고한 소켓만 돌려준다. 프로세스가 이미
    끝났거나 볼 권한이 없으면 그 프로세스는 건너뛴다.

    Args:
        pid: 트리의 뿌리 프로세스.

    Returns:
        열린 포트 목록. 같은 포트·주소는 한 번만.
    """
    try:
        root = psutil.Process(pid)
        tree = [root, *root.children(recursive=True)]
    except psutil.Error:
        return []
    found: set[Listen] = set()
    for proc in tree:
        try:
            sockets = proc.net_connections(kind="tcp")
        except psutil.Error:
            continue
        for sock in sockets:
            if sock.status == psutil.CONN_LISTEN and sock.laddr:
                found.add(Listen(sock.laddr.port, sock.laddr.ip, proc.pid))
    return sorted(found)
