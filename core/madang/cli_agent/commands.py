"""에이전트 명령의 Typer 연결.

명령은 task, decide, artifact, commit, push, view, runs, help이다.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from madang.cli_agent import client
from madang.cli_agent.artifacts import REPO_PREFIX
from madang.cli_agent.client import CoreClient
from madang.cli_agent.context import BY_ENV, AgentError
from madang.cli_agent.runs import runs_app
from madang.runners.base import PAGE_ENV

PageOption = Annotated[
    str | None,
    typer.Option(
        "--page",
        help=(
            "페이지 id. 에이전트 실행 밖에서는 필수이며 기본값은 $MADANG_PAGE."
        ),
    ),
]
HomeOption = Annotated[
    Path | None,
    typer.Option(
        "--home",
        help="앱 홈 디렉터리. 기본값은 $MADANG_HOME 또는 ~/.madang.",
    ),
]

OVERVIEW = """\
madang 에이전트 명령($MADANG_PAGE 또는 --page <id>의 페이지에 작용한다):

  madang task <id> --status S [--title T] [--due YYYY-MM-DD]
      ledger.md의 태스크를 추가하거나 갱신한다. S: todo | doing | blocked | review | done.
  madang decide <id> --topic T --choice C --options a,b,c [--supersedes D0]
      ledger.md에 결정을 기록한다.
  madang artifact add <path>
      이 페이지가 만든 파일을 등록한다(blocks/... 또는 프로젝트 폴더의 파일).
  madang commit -m "message"
      작업 트리(코드 페이지면 그 워크트리)의 모든 변경을 커밋한다.
  madang push
      작업 트리의 현재 브랜치를 푸시한다. 강제 푸시는 하지 않는다.
  madang view create --template T --data bNN [--data slot=bNN]
      템플릿으로 데이터 블록을 보여 주는 뷰 블록을 만든다.
  madang runs add --name N --command C [--cwd DIR] [--opens URL]
      실행할 수 있는 것을 만들었으면 config.yaml의 runs:에 선언한다.
  madang help [command]
      이 목록 또는 명령 하나의 옵션을 보여 준다.

모든 변경은 페이지 검증기로 검사하며, 검사에 실패하면 되돌린다.
"""  # noqa: E501

artifact_app = typer.Typer(
    help="ledger.md 산출물을 관리한다.",
    no_args_is_help=True,
    add_completion=False,
)
view_app = typer.Typer(
    help="뷰 블록을 관리한다.", no_args_is_help=True, add_completion=False
)


def _page_id(page: str | None) -> tuple[str, bool]:
    """페이지 id와, 그것을 ``MADANG_PAGE``에서 얻었는지 여부를 반환한다."""
    if page is not None:
        return page, False
    from_env = os.environ.get(PAGE_ENV)
    if not from_env:
        raise AgentError(
            f"{PAGE_ENV}가 설정돼 있지 않다. 에이전트 실행 밖에서는 "
            "--page <page-id>를 준다"
        )
    return from_env, True


def _default_by(from_env: bool) -> str:
    return "agent" if from_env else "human"


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(f"오류: {message}", err=True)
    return typer.Exit(code)


def _run(
    page: str | None,
    home: Path | None,
    action: Callable[[CoreClient, bool], str],
) -> None:
    """core에 요청을 보내고 결과 한 줄을 출력한다.

    거절은 종료 코드 1, core에 연결할 수 없으면 2로 끝낸다.
    """
    try:
        page_id, from_env = _page_id(page)
        core = CoreClient(client.open_transport(home), page_id)
        message = action(core, from_env)
    except AgentError as exc:
        raise _fail(str(exc)) from exc
    except client.RejectedError as exc:
        typer.echo(f"오류: {exc}", err=True)
        for issue in exc.issues:
            typer.echo(f"  {_issue_line(issue)}", err=True)
        raise typer.Exit(1) from exc
    except client.CoreUnreachableError as exc:
        raise _fail(str(exc), 2) from exc
    typer.echo(message)


def _issue_line(issue: dict[str, Any]) -> str:
    where = issue.get("path") or "-"
    if issue.get("line") is not None:
        where = f"{where}:{issue['line']}"
    return f"{where}: {issue.get('code')} {issue.get('message')}"


def _local_path(raw: str) -> str:
    """현재 폴더에 있는 상대 경로는 절대 경로로 바꿔 core에 보낸다."""
    if raw.startswith(REPO_PREFIX) or Path(raw).expanduser().is_absolute():
        return raw
    candidate = Path.cwd() / raw
    return str(candidate.resolve()) if candidate.exists() else raw


def task(
    task_id: Annotated[
        str, typer.Argument(metavar="ID", help="태스크 id. 예: T2.")
    ],
    status: Annotated[
        str,
        typer.Option("--status", help="todo | doing | blocked | review | done"),
    ],
    title: Annotated[
        str | None,
        typer.Option("--title", help="태스크 제목(새 태스크는 필수)."),
    ] = None,
    due: Annotated[
        str | None, typer.Option("--due", help="마감일, YYYY-MM-DD.")
    ] = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """ledger.md의 태스크를 추가하거나 갱신한다."""

    def act(core: CoreClient, from_env: bool) -> str:
        done = core.set_task(task_id, status, title, due)
        return f"태스크 {done['id']}: {done['status']}"

    _run(page, home, act)


def decide(
    decision_id: Annotated[
        str, typer.Argument(metavar="ID", help="결정 id. 예: D2.")
    ],
    topic: Annotated[str, typer.Option("--topic", help="무엇을 결정했는지.")],
    choice: Annotated[str, typer.Option("--choice", help="선택한 옵션.")],
    options: Annotated[
        str,
        typer.Option("--options", help="선택 항목을 포함한 쉼표 구분 옵션."),
    ],
    supersedes: Annotated[
        str | None,
        typer.Option("--supersedes", help="이 결정이 대체하는 결정의 id."),
    ] = None,
    state: Annotated[
        str,
        typer.Option(
            "--state", help="proposed | confirmed | superseded | deferred"
        ),
    ] = "confirmed",
    by: Annotated[
        str | None,
        typer.Option("--by", help="결정한 사람. 기본값은 $MADANG_BY."),
    ] = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """ledger.md에 결정을 기록한다."""

    def act(core: CoreClient, from_env: bool) -> str:
        done = core.decide(
            {
                "id": decision_id,
                "topic": topic,
                "choice": choice,
                "options": [o.strip() for o in options.split(",")],
                "state": state,
                "by": by or os.environ.get(BY_ENV) or _default_by(from_env),
                "in_run": from_env,
                **({"supersedes": supersedes} if supersedes else {}),
            }
        )
        suffix = f" ({supersedes} 대체)" if supersedes else ""
        return f"결정 {done['id']} 기록: {done['choice']}{suffix}"

    _run(page, home, act)


@artifact_app.command("add")
def artifact_add(
    path: Annotated[
        str,
        typer.Argument(
            help="페이지의 blocks/..., 프로젝트 폴더의 파일, 또는 repo:<path>.",
        ),
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """파일을 페이지의 산출물로 등록한다."""

    def act(core: CoreClient, from_env: bool) -> str:
        artifacts = core.add_artifact(_local_path(path))
        return f"산출물 등록됨(현재 {len(artifacts)}개): {path}"

    _run(page, home, act)


def commit(
    message: Annotated[
        str, typer.Option("-m", "--message", help="커밋 메시지.")
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """작업 트리(코드 페이지면 그 워크트리)의 모든 변경을 커밋한다."""

    def act(core: CoreClient, from_env: bool) -> str:
        return f"커밋했다: {core.commit(message, in_run=from_env)}"

    _run(page, home, act)


def push(page: PageOption = None, home: HomeOption = None) -> None:
    """작업 트리의 현재 브랜치를 푸시한다(강제 푸시 없음)."""

    def act(core: CoreClient, from_env: bool) -> str:
        pushed = core.push()
        return f"푸시했다: {pushed['branch']} -> {pushed['remote']}"

    _run(page, home, act)


@view_app.command("create")
def view_create(
    template: Annotated[
        str,
        typer.Option("--template", help="템플릿 이름. name@version도 가능."),
    ],
    data: Annotated[
        list[str],
        typer.Option(
            "--data",
            help="다음 슬롯의 데이터 블록 또는 slot=bNN. 반복 가능.",
        ),
    ],
    title: Annotated[
        str | None, typer.Option("--title", help="뷰 제목.")
    ] = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """데이터 블록에 묶인 뷰 블록을 만든다."""

    def act(core: CoreClient, from_env: bool) -> str:
        made = core.create_view(template, data, title, in_run=from_env)
        return f"뷰 {made['id']} 생성({made['file']})"

    _run(page, home, act)


def register(root: typer.Typer) -> None:
    """에이전트 명령을 루트 ``madang`` 앱에 추가한다.

    Args:
        root: 루트 ``madang`` Typer 앱.
    """
    root.command()(task)
    root.command()(decide)
    root.add_typer(artifact_app, name="artifact")
    root.command()(commit)
    root.command()(push)
    root.add_typer(view_app, name="view")
    root.add_typer(runs_app, name="runs")

    @root.command("help")
    def help_command(
        command: Annotated[
            list[str] | None,
            typer.Argument(
                metavar="[COMMAND]...",
                help="명령. 예: task, view create.",
            ),
        ] = None,
    ) -> None:
        """에이전트 명령 사용법을 보여 준다."""
        if not command:
            typer.echo(OVERVIEW, nl=False)
            return
        group = typer.main.get_command(root)
        try:
            group.main(
                args=[*command, "--help"],
                prog_name="madang",
                standalone_mode=False,
            )
        except Exception as exc:  # 알 수 없는 명령
            raise _fail(f"알 수 없는 명령 '{' '.join(command)}'") from exc
