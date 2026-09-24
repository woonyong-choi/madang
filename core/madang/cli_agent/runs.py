"""``madang runs``: 실행 대상을 선언하고, 선언된 것만 core에서 실행한다.

명령은 core API로 요청한다. 선언은 ``<project>/.madang/config.yaml``의
``runs:``에 남고, 실행은 core가 소유한 프로세스로 돌며 정책
(``policy.deny``)을 지난다. 명령을 짐작하지 않는다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import typer

from madang.cli_agent import client
from madang.cli_agent.client import CoreClient, quoted
from madang.runners.base import PAGE_ENV

runs_app = typer.Typer(
    help="실행 대상(config.yaml의 runs:)을 선언하고 core에서 실행한다.",
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


class _RefusedError(Exception):
    """명령을 진행할 수 없다."""


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(f"오류: {message}", err=True)
    return typer.Exit(code)


def _request(
    home: Path | None,
    project: str | None,
    page: str | None,
    method: str,
    tail: str,
    payload: Any = None,
) -> Any:
    """명령이 작용할 프로젝트의 ``/projects/<id>/runs...``로 요청한다.

    거절은 종료 코드 1, core에 연결할 수 없으면 2로 끝낸다.
    """
    try:
        transport = client.open_transport(home)
        if project is None:
            page_id = page or os.environ.get(PAGE_ENV)
            if not page_id:
                raise _RefusedError(
                    f"--project를 주거나 --page 또는 {PAGE_ENV}로 페이지를 준다"
                )
            project = CoreClient(transport, page_id).project()
        path = f"/projects/{quoted(project)}/runs{tail}"
        return client.call(transport, method, path, payload)
    except _RefusedError as exc:
        raise _fail(str(exc)) from exc
    except client.RejectedError as exc:
        raise _fail(str(exc)) from exc
    except client.CoreUnreachableError as exc:
        raise _fail(str(exc), 2) from exc


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
    payload = {"name": name, "command": command, "cwd": cwd}
    if opens:
        payload["opens"] = opens
    _request(home, project, page, "POST", "", payload)
    typer.echo(f"실행 대상 선언: {name}")


@runs_app.command("list")
def list_(
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """선언된 실행 대상을 한 줄에 하나씩 출력한다.

    열은 이름, 폴더, 명령, URL, 상태(running | stopped)다.
    """
    for target in _request(home, project, page, "GET", ""):
        fields = (
            target["name"],
            target["cwd"],
            target["command"],
            target.get("opens") or "-",
            "running" if target["running"] else "stopped",
        )
        typer.echo("\t".join(fields))


@runs_app.command("start")
def start(
    name: NameArgument,
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """선언된 실행 대상을 core에서 시작한다. `madang runs stop`으로 끝낸다.

    출력과 열린 URL은 core가 앱에 이벤트로 보낸다.
    """
    status = _request(home, project, page, "POST", f"/{quoted(name)}/start")
    typer.echo(f"시작: {name} (pid {status.get('pid', '-')})")


@runs_app.command("stop")
def stop(
    name: NameArgument,
    project: ProjectOption = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """core에서 돌고 있는 실행 대상을 자손 프로세스까지 정지한다."""
    _request(home, project, page, "POST", f"/{quoted(name)}/stop")
    typer.echo(f"정지: {name}")
