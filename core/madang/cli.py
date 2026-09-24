"""madang command line entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from madang import __version__, config
from madang.store.git import GitError
from madang.store.home import init_home

app = typer.Typer(
    name="madang",
    help="Madang core command line.",
    no_args_is_help=True,
    add_completion=False,
)

HomeOption = Annotated[
    Optional[Path],
    typer.Option("--home", help="App home directory. Defaults to $MADANG_HOME or ~/.madang."),
]


def _version(value: bool) -> None:
    if value:
        typer.echo(f"madang {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    """Madang core command line."""


@app.command()
def init(home: HomeOption = None) -> None:
    """Create the app home (config, root memory, root space, git repository)."""
    path = config.resolve_home(home)
    try:
        result = init_home(path)
    except (GitError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if result.created:
        typer.echo(f"initialized {path} ({len(result.created)} files)")
    elif result.committed:
        typer.echo(f"initialized {path} (committed existing files)")
    else:
        typer.echo(f"already initialized: {path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
