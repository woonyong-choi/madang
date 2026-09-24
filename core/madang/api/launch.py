"""실행 대상 이벤트를 앱 이벤트로 옮기고, 열린 포트를 관찰한다.

포트는 운영체제가 알려 주는 사실만 쓴다. core가 띄운 실행 대상의
프로세스 트리와, 작업 폴더가 프로젝트 폴더(또는 그 워크트리 폴더) 안인
프로세스가 LISTEN 중인 TCP 포트다. 명령이나 포트 번호를 짐작하지 않는다.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Any

import psutil

from madang import runs
from madang.api import events
from madang.store import projects
from madang.store.page import WORKTREES_SUFFIX

log = logging.getLogger(__name__)


def relay_run_event(core: Any, kind: str, payload: dict[str, Any]) -> None:
    """실행 대상 프로세스의 이벤트를 앱 이벤트로 옮긴다.

    출력 줄은 ``run.log``, 준비된 URL은 ``runs.opened``, 열기와 종료 뒤의
    포트는 ``ports.changed``다.
    """
    try:
        project = _project_at(core, Path(payload["root"]))
        if project is None:
            return
        name = payload["name"]
        where = {"project": project.id}
        if kind == runs.RUN_OUTPUT:
            core.hub.emit(
                events.RUN_LOG, {"name": name, "line": payload["line"]}, **where
            )
        elif kind == runs.RUN_OPEN:
            core.hub.emit(
                events.RUNS_OPENED,
                {"name": name, "url": payload["url"]},
                **where,
            )
            announce_ports(core, project, name)
        elif kind in (runs.RUN_EXITED, runs.RUN_STOPPED):
            core.hub.emit(
                events.RUN_LOG,
                {"name": name, "line": "", "exit_code": payload["code"]},
                **where,
            )
            announce_ports(core, project, name)
    except Exception:
        log.exception("cannot relay %s", kind)


def announce_ports(core: Any, project: projects.Project, name: str) -> None:
    """프로젝트의 지금 열린 포트를 ``ports.changed``로 알린다."""
    data = {"name": name, "ports": observe(core, project)}
    core.hub.emit(events.PORTS_CHANGED, data, project=project.id)


def _project_at(core: Any, root: Path) -> projects.Project | None:
    real = root.resolve()
    for project in projects.load(core.home):
        if project.root.resolve() == real:
            return project
    return None


def observe(core: Any, project: projects.Project) -> list[dict[str, Any]]:
    """프로젝트에서 지금 LISTEN 중인 포트를 포트 순으로 반환한다.

    Args:
        core: ``Core``. 실행 대상 프로세스를 맡은 감독을 쓴다.
        project: 프로젝트.

    Returns:
        ``{port, host, pid, command, cwd, run}`` 목록. ``cwd``는 프로젝트
        (또는 워크트리) 기준 경로이고, ``run``은 core가 띄운 실행 대상의
        이름이다.
    """
    owners = _supervised(core, project.root)
    found: dict[tuple[int, str], dict[str, Any]] = {}
    for proc in _processes_in(project.root, owners):
        try:
            sockets = proc.net_connections(kind="tcp")
            command = shlex.join(proc.cmdline())
            cwd = _relative(project.root, Path(proc.cwd()))
        except psutil.Error:
            continue
        for sock in sockets:
            if sock.status != psutil.CONN_LISTEN or not sock.laddr:
                continue
            key = (sock.laddr.port, sock.laddr.ip)
            found.setdefault(
                key,
                {
                    "port": sock.laddr.port,
                    "host": sock.laddr.ip,
                    "pid": proc.pid,
                    "command": command,
                    "cwd": cwd,
                    "run": owners.get(proc.pid),
                },
            )
    return [found[key] for key in sorted(found)]


def _supervised(core: Any, root: Path) -> dict[int, str]:
    """core가 띄운 이 프로젝트 실행 대상의 프로세스 트리: pid -> 이름."""
    owners: dict[int, str] = {}
    real = root.resolve()
    for proc in core.supervisor.running():
        if proc.root.resolve() != real or proc.pid is None:
            continue
        try:
            tree = psutil.Process(proc.pid)
            members = [tree, *tree.children(recursive=True)]
        except psutil.Error:
            continue
        for member in members:
            owners[member.pid] = proc.target.name
    return owners


def _processes_in(root: Path, owners: dict[int, str]) -> list[psutil.Process]:
    """작업 폴더가 프로젝트나 그 워크트리 폴더 안인 프로세스와 감독 대상."""
    bases = [root.resolve(), _worktrees_dir(root).resolve()]
    found = []
    for proc in psutil.process_iter(["cwd"]):
        cwd = proc.info.get("cwd")
        inside = cwd is not None and any(
            Path(cwd).is_relative_to(base) for base in bases
        )
        if inside or proc.pid in owners:
            found.append(proc)
    return found


def _worktrees_dir(root: Path) -> Path:
    return root.parent / f"{root.name}{WORKTREES_SUFFIX}"


def _relative(root: Path, cwd: Path) -> str | None:
    """프로젝트 기준 경로. 워크트리 폴더 안이면 그 워크트리 기준 경로."""
    real = cwd.resolve()
    if real.is_relative_to(root.resolve()):
        return real.relative_to(root.resolve()).as_posix() or "."
    trees = _worktrees_dir(root).resolve()
    if real.is_relative_to(trees):
        parts = real.relative_to(trees).parts[1:]
        return Path(*parts).as_posix() if parts else "."
    return None
