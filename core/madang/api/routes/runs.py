"""실행 대상 경로: 선언(``runs:``), 시작·정지, 관찰한 포트와 그 선언.

실행할 수 있는 것은 프로젝트 ``config.yaml``의 ``runs:``에 선언된 것뿐이다.
프로세스는 core가 소유하고, 출력은 ``run.log``, 준비된 URL은
``runs.opened``, 포트 변화는 ``ports.changed``로 알린다. 시작 전에 정책의
금지 명령(``policy.deny``)을 확인한다.
"""

from __future__ import annotations

import threading
from pathlib import Path

from madang import config
from madang import runs as targets
from madang.api import errors, launch, models, workspace
from madang.api.core import Core
from madang.api.routes import CoreDep, Router
from madang.store import projects

router = Router(tags=["runs"])


def _declared(project: projects.Project) -> list[config.RunTarget]:
    try:
        return targets.targets(project.root)
    except (OSError, config.ConfigError) as exc:
        raise errors.invalid(f"cannot load project config: {exc}") from exc


def _target(project: projects.Project, name: str) -> config.RunTarget:
    for target in _declared(project):
        if target.name == name:
            return target
    raise errors.not_found(f"run '{name}' is not declared in runs:")


def _process(core: Core, root: Path, name: str) -> targets.Process | None:
    try:
        return core.supervisor.get(root, name)
    except targets.RunsError:
        return None


def target_status(
    core: Core, project: projects.Project, target: config.RunTarget
) -> models.RunTargetStatus:
    """선언된 실행 대상과 core가 띄운 프로세스의 지금 상태."""
    proc = _process(core, project.root, target.name)
    running = proc is not None and proc.running
    ports = [
        models.ObservedPort(
            port=p.port, host=p.host, pid=p.pid, run=target.name
        )
        for p in (proc.ports() if proc is not None and running else [])
    ]
    return models.RunTargetStatus(
        **target.model_dump(),
        running=running,
        pid=proc.pid if running and proc is not None else None,
        ports=ports,
    )


@router.get("/projects/{project}/runs", operation_id="listRunTargets")
def list_targets(project: str, core: CoreDep) -> list[models.RunTargetStatus]:
    """선언된 실행 대상과 상태, 선언 순서."""
    found = core.project(project)
    return [target_status(core, found, t) for t in _declared(found)]


@router.post(
    "/projects/{project}/runs",
    status_code=201,
    operation_id="declareRunTarget",
)
def declare_target(
    project: str, body: models.RunDeclare, core: CoreDep
) -> models.RunTargetStatus:
    """실행 대상을 ``runs:``에 선언한다. 다른 절과 주석은 그대로다."""
    found = core.project(project)
    return _declare(core, found, body.name, body.command, body.cwd, body.opens)


def _declare(
    core: Core,
    project: projects.Project,
    name: str,
    command: str,
    cwd: str,
    opens: str | None,
) -> models.RunTargetStatus:
    with core.lock:
        try:
            target = targets.declare(
                project.root, name, command, cwd=cwd, opens=opens
            )
        except targets.RunsError as exc:
            raise errors.invalid(str(exc)) from exc
        except (OSError, config.ConfigError) as exc:
            raise errors.invalid(f"cannot declare run: {exc}") from exc
    return target_status(core, project, target)


@router.post(
    "/projects/{project}/runs/{name}/start", operation_id="startRunTarget"
)
def start_target(
    project: str, name: str, core: CoreDep
) -> models.RunTargetStatus:
    """선언된 실행 대상을 core 소유 프로세스로 시작한다.

    ``opens``가 있으면 그 URL이 응답할 때 ``runs.opened``를 낸다.
    """
    found = core.project(project)
    target = _target(found, name)
    workspace.allow(found, target.command)
    try:
        proc = core.supervisor.start(found.root, name)
    except targets.RunsError as exc:
        raise errors.conflict(str(exc)) from exc
    except OSError as exc:
        raise errors.conflict(f"cannot start run '{name}': {exc}") from exc
    if target.opens:
        threading.Thread(
            target=proc.wait_opens, name=f"opens-{name}", daemon=True
        ).start()
    return target_status(core, found, target)


@router.post(
    "/projects/{project}/runs/{name}/stop", operation_id="stopRunTarget"
)
def stop_target(
    project: str, name: str, core: CoreDep
) -> models.RunTargetStatus:
    """core가 띄운 실행 대상을 자손 프로세스까지 정지한다."""
    found = core.project(project)
    target = _target(found, name)
    proc = _process(core, found.root, name)
    if proc is None or not proc.running:
        raise errors.conflict(f"run '{name}' is not running")
    proc.stop()
    return target_status(core, found, target)


@router.get("/projects/{project}/ports", operation_id="listPorts")
def list_ports(project: str, core: CoreDep) -> list[models.ObservedPort]:
    """프로젝트에서 지금 열린 포트(관찰)."""
    found = core.project(project)
    return [
        models.ObservedPort.model_validate(p)
        for p in launch.observe(core, found)
    ]


@router.post(
    "/projects/{project}/ports/{port}/declare",
    status_code=201,
    operation_id="declarePort",
)
def declare_port(
    project: str, port: int, body: models.PortDeclare, core: CoreDep
) -> models.RunTargetStatus:
    """관찰한 포트를 연 프로세스를 ``runs:``에 선언한다.

    명령과 폴더는 요청에 없으면 그 프로세스의 실제 명령줄과 작업 폴더를
    쓴다. ``opens``는 ``http://localhost:<port>``다.
    """
    found = core.project(project)
    observed = next(
        (p for p in launch.observe(core, found) if p["port"] == port), None
    )
    if observed is None:
        raise errors.not_found(f"port {port} is not open in '{project}'")
    command = body.command or observed["command"]
    cwd = body.cwd or observed["cwd"] or "."
    if not command:
        raise errors.invalid(f"command of port {port} is unknown; give one")
    return _declare(
        core, found, body.name, command, cwd, f"http://localhost:{port}"
    )
