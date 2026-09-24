"""``madang runs``: 실행 대상을 선언하고, 선언된 것만 실행한다.

명령은 core의 ``runs`` 모듈을 거친다. 명령을 짐작하지 않으며, 실행할 수
있는 것은 ``<project>/.madang/config.yaml``의 ``runs:``에 있는 것뿐이다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import typer

from madang import config, runs
from madang.runners.base import PAGE_ENV
from madang.runs import pidfile
from madang.runs.process import OPENS_SECONDS, stop_group
from madang.store import pages, projects

runs_app = typer.Typer(
    help="실행 대상(config.yaml의 runs:)을 선언하고 실행한다.",
    no_args_is_help=True,
    add_completion=False,
)

ProjectOption = Annotated[
    str | None,
    typer.Option(
        "--project",
        help="프로젝트 id. 없으면 --page 또는 $MADANG_PAGE 페이지의 프로젝트.",
    ),
]
PageOption = Annotated[
    str | None,
    typer.Option("--page", help="페이지 id. 기본값은 $MADANG_PAGE."),
]
HomeOption = Annotated[
    Path | None,
    typer.Option(
        "--home",
        help="앱 홈 디렉터리. 기본값은 $MADANG_HOME 또는 ~/.madang.",
    ),
]
NameArgument = Annotated[str, typer.Argument(help="실행 대상 이름.")]


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(f"오류: {message}", err=True)
    return typer.Exit(code)


def _project(
    home: Path | None, project: str | None, page: str | None
) -> tuple[Path, projects.Project]:
    """앱 홈과, 명령이 작용할 프로젝트를 정한다."""
    root = config.resolve_home(home)
    try:
        if project is not None:
            return root, projects.get(root, project)
        page_id = page or os.environ.get(PAGE_ENV)
        if not page_id:
            raise _fail(
                f"--project를 주거나 --page 또는 {PAGE_ENV}로 페이지를 준다"
            )
        return root, projects.owner(root, pages.find_page(root, page_id))
    except (FileNotFoundError, pages.PageNotFoundError) as exc:
        raise _fail(str(exc)) from exc


def _target(found: projects.Project, name: str) -> config.RunTarget:
    try:
        return runs.find(found.root, name)
    except (OSError, config.ConfigError, runs.RunsError) as exc:
        raise _fail(str(exc)) from exc


@runs_app.command("add")
def add(
    name: Annotated[str, typer.Option("--name", help="실행 대상 이름.")],
    command: Annotated[str, typer.Option("--command", help="셸 명령.")],
    cwd: Annotated[
        str, typer.Option("--cwd", help="프로젝트 폴더 기준 실행 폴더.")
    ] = ".",
    opens: Annotated[
        str | None,
        typer.Option("--opens", help="준비되면 브라우저로 열 URL."),
    ] = None,
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """실행 대상을 config.yaml의 runs:에 선언한다."""
    _, found = _project(home, project, page)
    try:
        runs.declare(found.root, name, command, cwd=cwd, opens=opens)
    except (OSError, config.ConfigError, runs.RunsError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"실행 대상 선언: {name}")


@runs_app.command("list")
def list_(
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """선언된 실행 대상을 한 줄에 하나씩(이름, 폴더, 명령, URL) 출력한다."""
    _, found = _project(home, project, page)
    try:
        declared = runs.targets(found.root)
    except (OSError, config.ConfigError) as exc:
        raise _fail(str(exc)) from exc
    for target in declared:
        fields = (target.name, target.cwd, target.command, target.opens or "-")
        typer.echo("\t".join(fields))


@runs_app.command("start")
def start(
    name: NameArgument,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="opens URL 응답을 기다릴 최대 초."),
    ] = OPENS_SECONDS,
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """선언된 실행 대상을 앞에서 실행한다. Ctrl-C나 runs stop으로 끝낸다.

    opens가 있으면 응답할 때까지 기다린 뒤 URL과 열린 포트를 알린다.
    """
    root, found = _project(home, project, page)
    target = _target(found, name)
    if pidfile.read(root, found.id, name) is not None:
        raise _fail(f"run '{name}' is already running")
    proc = runs.Process(target, found.root, _echo)
    try:
        proc.start()
    except (OSError, runs.RunsError) as exc:
        raise _fail(str(exc)) from exc
    assert proc.pid is not None
    pidfile.write(root, found.id, name, proc.pid)
    try:
        if proc.wait_opens(timeout):
            _echo_ports(proc.ports())
        code = proc.wait()
    except KeyboardInterrupt:
        code = proc.stop()
    finally:
        pidfile.remove(root, found.id, name)
    raise typer.Exit(max(code or 0, 0))


@runs_app.command("stop")
def stop(
    name: NameArgument,
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """`madang runs start`로 돌고 있는 실행 대상을 자손까지 정지한다."""
    root, found = _project(home, project, page)
    pid = pidfile.read(root, found.id, name)
    if pid is None:
        raise _fail(f"run '{name}' is not running")
    stop_group(pid)
    pidfile.remove(root, found.id, name)
    typer.echo(f"정지: {name}")


def _echo(kind: str, payload: dict[str, Any]) -> None:
    """출력 줄은 표준 출력에, 나머지 알림은 표준 오류에 쓴다."""
    if kind == runs.RUN_OUTPUT:
        typer.echo(payload["line"])
    elif kind == runs.RUN_OPEN:
        typer.echo(f"열기: {payload['url']}", err=True)
    elif kind in (runs.RUN_EXITED, runs.RUN_STOPPED):
        typer.echo(f"종료: {payload['name']} ({payload['code']})", err=True)


def _echo_ports(ports: list[runs.Listen]) -> None:
    for listen in ports:
        typer.echo(
            f"포트: {listen.host}:{listen.port} (pid {listen.pid})", err=True
        )
