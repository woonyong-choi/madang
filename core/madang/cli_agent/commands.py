"""Typer wiring for the agent commands.

The commands are task, decide, artifact, commit, push, promote, view, and help.
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
            "Page id. Required outside an agent run; defaults to $MADANG_PAGE."
        ),
    ),
]
HomeOption = Annotated[
    Path | None,
    typer.Option(
        "--home",
        help="App home directory. Defaults to $MADANG_HOME or ~/.madang.",
    ),
]

OVERVIEW = """\
madang agent commands (act on the page in $MADANG_PAGE, or --page <id>):

  madang task <id> --status S [--title T] [--due YYYY-MM-DD]
      Add or update a task in state.md. S: todo | doing | blocked | review | done.
  madang decide <id> --topic T --choice C --options a,b,c [--supersedes D0]
      Record a decision in state.md.
  madang artifact add <path>
      Register a file this page made (blocks/... or a file in the code repository).
  madang commit -m "message"
      Commit every change in the space's code repository.
  madang push
      Push the current branch of the code repository. Never forces.
  madang promote <bNN>
      Copy a block file to docs/ in the code repository and commit it.
  madang view create --template T --data bNN [--data slot=bNN]
      Create a view block that shows data blocks with a template.
  madang help [command]
      Show this list, or the options of one command.

Every change is checked against the page validators and undone when a check fails.
"""  # noqa: E501

artifact_app = typer.Typer(
    help="Manage state.md artifacts.",
    no_args_is_help=True,
    add_completion=False,
)
view_app = typer.Typer(
    help="Manage view blocks.", no_args_is_help=True, add_completion=False
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
        str, typer.Argument(metavar="ID", help="Task id, e.g. T2.")
    ],
    status: Annotated[
        str,
        typer.Option("--status", help="todo | doing | blocked | review | done"),
    ],
    title: Annotated[
        str | None,
        typer.Option("--title", help="Task title (required for a new task)."),
    ] = None,
    due: Annotated[
        str | None, typer.Option("--due", help="Due date, YYYY-MM-DD.")
    ] = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """Add or update a task in state.md."""
    _run(page, home, lambda ctx: ops.set_task(ctx, task_id, status, title, due))


def decide(
    decision_id: Annotated[
        str, typer.Argument(metavar="ID", help="Decision id, e.g. D2.")
    ],
    topic: Annotated[str, typer.Option("--topic", help="What was decided.")],
    choice: Annotated[str, typer.Option("--choice", help="The chosen option.")],
    options: Annotated[
        str,
        typer.Option(
            "--options", help="Comma separated options, including the choice."
        ),
    ],
    supersedes: Annotated[
        str | None,
        typer.Option(
            "--supersedes", help="Id of the decision this one replaces."
        ),
    ] = None,
    state: Annotated[
        str,
        typer.Option(
            "--state", help="proposed | confirmed | superseded | deferred"
        ),
    ] = "confirmed",
    by: Annotated[
        str | None,
        typer.Option("--by", help="Who decided. Defaults to $MADANG_BY."),
    ] = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """Record a decision in state.md."""
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
            help=(
                "blocks/... in the page, a file in the code repository, "
                "or repo:<path>."
            )
        ),
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """Register a file as an artifact of the page."""
    _run(page, home, lambda ctx: ops.add_artifact(ctx, path))


def commit(
    message: Annotated[
        str, typer.Option("-m", "--message", help="Commit message.")
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """Commit all changes in the space's code repository."""
    _run(page, home, lambda ctx: ops.commit(ctx, message))


def push(page: PageOption = None, home: HomeOption = None) -> None:
    """Push the current branch of the code repository (no force)."""
    _run(page, home, ops.push)


def promote(
    block: Annotated[
        str, typer.Argument(metavar="BLOCK", help="Block id, e.g. b05.")
    ],
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """Copy a block file to docs/ in the code repository and commit it."""
    _run(page, home, lambda ctx: ops.promote(ctx, block))


@view_app.command("create")
def view_create(
    template: Annotated[
        str,
        typer.Option(
            "--template", help="Template name, optionally name@version."
        ),
    ],
    data: Annotated[
        list[str],
        typer.Option(
            "--data",
            help="Data block for the next slot, or slot=bNN. Repeatable.",
        ),
    ],
    title: Annotated[
        str | None, typer.Option("--title", help="View title.")
    ] = None,
    page: PageOption = None,
    home: HomeOption = None,
) -> None:
    """Create a view block bound to data blocks."""
    _run(page, home, lambda ctx: ops.create_view(ctx, template, data, title))


def register(root: typer.Typer) -> None:
    """Adds the agent commands to the root ``madang`` app.

    Args:
        root: The root ``madang`` Typer app.
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
                help="Command, e.g. task or view create.",
            ),
        ] = None,
    ) -> None:
        """Show agent command usage."""
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
        except Exception as exc:  # unknown command
            typer.echo(
                f"error: unknown command '{' '.join(command)}'", err=True
            )
            raise typer.Exit(1) from exc
