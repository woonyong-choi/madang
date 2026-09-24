"""madang command line entry point."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from madang import __version__, config
from madang.store.git import GitError
from madang.store.home import init_home
from madang.validate import validate_target

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


@app.command()
def validate(
    target: Annotated[Path, typer.Argument(help="state.md path or page folder.")],
    repo: Annotated[
        Optional[Path],
        typer.Option("--repo", help="Code repository for repo: artifacts. Defaults to repo in space.md."),
    ] = None,
    home: HomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print issues as JSON.")] = False,
) -> None:
    """Check state.md (and page.md) of a page. Exit 1 when issues are found."""
    if not target.exists():
        typer.echo(f"error: {target} does not exist", err=True)
        raise typer.Exit(2)
    try:
        cfg = config.load_config(home)
    except Exception as exc:
        typer.echo(f"error: cannot load config: {exc}", err=True)
        raise typer.Exit(2) from exc
    issues = validate_target(
        target,
        repo=repo.expanduser() if repo is not None else None,
        token_limit=cfg.madang.limits.state_tokens,
        kinds=cfg.routes.kinds,
    )
    if as_json:
        payload = {"ok": not issues, "issues": [issue.to_dict() for issue in issues]}
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            typer.echo(issue.format())
    if issues:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
