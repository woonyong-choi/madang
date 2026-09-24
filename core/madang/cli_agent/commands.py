"""에이전트 명령의 Typer 연결.

명령은 task, decide, artifact, commit, push, promote, view, help이다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from madang.cli_agent import ops
from madang.cli_agent.context import (
    AgentError,
    PageContext,
    PageValidationError,
    resolve,
)
from madang.store import frontmatter, git

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
      state.md의 태스크를 추가하거나 갱신한다. S: todo | doing | blocked | review | done.
  madang decide <id> --topic T --choice C --options a,b,c [--supersedes D0]
      state.md에 결정을 기록한다.
  madang artifact add <path>
      이 페이지가 만든 파일을 등록한다(blocks/... 또는 코드 저장소의 파일).
  madang commit -m "message"
      스페이스 코드 저장소의 모든 변경을 커밋한다.
  madang push
      코드 저장소의 현재 브랜치를 푸시한다. 강제 푸시는 하지 않는다.
  madang promote <bNN>
      블록 파일을 코드 저장소의 docs/로 복사하고 커밋한다.
  madang view create --template T --data bNN [--data slot=bNN]
      템플릿으로 데이터 블록을 보여 주는 뷰 블록을 만든다.
  madang help [command]
      이 목록 또는 명령 하나의 옵션을 보여 준다.

모든 변경은 페이지 검증기로 검사하며, 검사에 실패하면 되돌린다.
"""  # noqa: E501

artifact_app = typer.Typer(
    help="state.md 산출물을 관리한다.",
    no_args_is_help=True,
    add_completion=False,
)
view_app = typer.Typer(
    help="뷰 블록을 관리한다.", no_args_is_help=True, add_completion=False
)


def _run(
    page: str | None, home: Path | None, action: Callable[[PageContext], str]
) -> None:
    try:
        ctx = resolve(page, home)
        message = action(ctx)
    except PageValidationError as exc:
        typer.echo(f"error: {exc}", err=True)
        for issue in exc.issues:
            typer.echo(f"  {issue.format()}", err=True)
        raise typer.Exit(1) from exc
    except (
        AgentError,
        frontmatter.FrontmatterError,
        git.GitError,
        OSError,
    ) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(message)


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
    """state.md의 태스크를 추가하거나 갱신한다."""
    _run(page, home, lambda ctx: ops.set_task(ctx, task_id, status, title, due))


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
    """state.md에 결정을 기록한다."""
    _run(
        page,
        home,
        lambda ctx: ops.decide(
            ctx,
            decision_id,
            topic=topic,
            choice=choice,
            options=options,
            supersedes=supersedes,
            state=state,
            by=by,
        ),
    )


@artifact_app.command("add")
def artifact_add(
    path: Annotated[
        str,
        typer.Argument(
            help=("페이지의 blocks/..., 코드 저장소의 파일, 또는 repo:<path>.")
        ),
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """파일을 페이지의 산출물로 등록한다."""
    _run(page, home, lambda ctx: ops.add_artifact(ctx, path))


def commit(
    message: Annotated[
        str, typer.Option("-m", "--message", help="커밋 메시지.")
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """스페이스 코드 저장소의 모든 변경을 커밋한다."""
    _run(page, home, lambda ctx: ops.commit(ctx, message))


def push(page: PageOption = None, home: HomeOption = None) -> None:
    """코드 저장소의 현재 브랜치를 푸시한다(강제 푸시 없음)."""
    _run(page, home, ops.push)


def promote(
    block: Annotated[
        str, typer.Argument(metavar="BLOCK", help="블록 id. 예: b05.")
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """블록 파일을 코드 저장소의 docs/로 복사하고 커밋한다."""
    _run(page, home, lambda ctx: ops.promote(ctx, block))


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
    _run(page, home, lambda ctx: ops.create_view(ctx, template, data, title))


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
    root.command()(promote)
    root.add_typer(view_app, name="view")

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
            typer.echo(
                f"error: unknown command '{' '.join(command)}'", err=True
            )
            raise typer.Exit(1) from exc
