"""madang command line entry point."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from madang import __version__, cli_agent, config
from madang.assemble import assemble
from madang.cli_agent.context import BY_ENV
from madang.runners import make_runner
from madang.runners.base import CliRunner
from madang.runners.record import RecordedRun, run_page
from madang.store import changes, frontmatter, git, pages, runs
from madang.store.git import GitError
from madang.store.home import NotAHomeError, init_home
from madang.store.log import append_message
from madang.store.page import (
    SPACE_FILE,
    STATE_FILE,
    space_dir,
    space_repo,
    work_dir,
)
from madang.validate import Issue, validate_target

app = typer.Typer(
    name="madang",
    help="Madang core command line.",
    no_args_is_help=True,
    add_completion=False,
)

HomeOption = Annotated[
    Path | None,
    typer.Option(
        "--home",
        help="App home directory. Defaults to $MADANG_HOME or ~/.madang.",
    ),
]


def _version(value: bool) -> None:
    if value:
        typer.echo(f"madang {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Madang core command line."""


@app.command()
def init(home: HomeOption = None) -> None:
    """Create the app home (config, root memory, root space, git repository)."""
    path = config.resolve_home(home)
    try:
        result = init_home(path)
    except (GitError, NotAHomeError, OSError) as exc:
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
    target: Annotated[
        Path, typer.Argument(help="state.md path or page folder.")
    ],
    repo: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            help=(
                "Code repository for repo: artifacts. "
                "Defaults to repo in space.md."
            ),
        ),
    ] = None,
    home: HomeOption = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print issues as JSON.")
    ] = False,
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
        payload = {
            "ok": not issues,
            "issues": [issue.to_dict() for issue in issues],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            typer.echo(issue.format())
    if issues:
        raise typer.Exit(1)


# single run

SCRATCH_DIR = "scratch"
REPO_PREFIX = "repo:"
# Page files that core writes itself; never reported as run output.
_BOOKKEEPING = (pages.LOG_FILE, f"{pages.BLOCKS_DIR}/{pages.LAST_BLOCK_FILE}")
_BOOKKEEPING_DIRS = (f"{runs.RUNS_DIR}/", f"{SCRATCH_DIR}/")
_SUMMARY_FILES = 3


@dataclass
class RunOutcome:
    """A finished single run of a page.

    Attributes:
        recorded: The run and its record.
        issues: What the state check found after the run.
        commit: The short hash of the app home commit.
    """

    recorded: RecordedRun
    issues: list[Issue]
    commit: str

    @property
    def ok(self) -> bool:
        """Whether the runner finished and the page passed its checks."""
        return self.recorded.result.status == "done" and not self.issues


def execute_run(
    page_dir: Path,
    runner: CliRunner,
    *,
    cfg: config.Config,
    model: str,
    effort: str,
    request: str,
    target: str | None = None,
) -> RunOutcome:
    """Runs one step of a page in a fresh session and commits the result.

    The request is logged, the prompt is assembled and saved to
    ``scratch/``, the runner works in the space's code repository (else the
    page folder), and then the page is checked, the run is recorded, the
    answer is logged, and the app home is committed.

    Args:
        page_dir: The page folder.
        runner: The runner to use.
        cfg: The app home configuration.
        model: The model name.
        effort: The reasoning effort.
        request: The message text.
        target: The block the request is about, or None for the page.

    Returns:
        The finished run.

    Raises:
        GitError: The app home commit fails.
        OSError: A page file cannot be read or written.
        ValueError: The target block has no file.
    """
    state = pages.read_header(page_dir / STATE_FILE)
    tier = int(state.get("tier") or 1)
    kind = str(state.get("kind") or cfg.routes.default_kind)
    cwd = work_dir(page_dir)
    if target is not None and not pages.block_files(page_dir, target):
        raise ValueError(f"block '{target}' has no file in blocks/")

    message = append_message(
        page_dir, "user", request, {"target": target or "page"}
    )
    assembled = assemble(
        page_dir, target, request, tier, cfg=cfg, runner=runner.name
    )
    prompt = assembled.prompt
    scratch = page_dir / SCRATCH_DIR
    scratch.mkdir(exist_ok=True)
    (scratch / f"{message}.prompt.md").write_text(prompt, encoding="utf-8")

    before = _snapshots(page_dir, cwd)
    with _environment(BY_ENV, f"{runner.name}/{model}"):
        recorded = run_page(
            runner,
            config=cfg,
            page_dir=page_dir,
            cwd=cwd,
            prompt=prompt,
            model=model,
            effort=effort,
            kind=kind,
            tier=tier,
            trigger={"message": message, "target": target or "page"},
            input=assembled.estimate(),
        )
    changed, unknown = _run_output(page_dir, cwd, before)
    issues = validate_target(
        page_dir,
        repo=space_repo(page_dir),
        token_limit=cfg.madang.limits.state_tokens,
        kinds=cfg.routes.kinds,
    )
    _finish_record(
        page_dir, recorded, assembled.contract, (changed, unknown), issues
    )

    result = recorded.result
    answer = result.final_text if result.status == "done" else None
    append_message(
        page_dir,
        "agent",
        answer or f"{result.status}: {result.error or 'no answer'}",
        {"run": recorded.n},
    )
    commit = _commit_run(page_dir, cfg.home, recorded, changed)
    return RunOutcome(recorded=recorded, issues=issues, commit=commit)


def run_commit_message(
    page_id: str, n: int, runner: str, model: str, changed: list[str]
) -> str:
    """Returns the app home commit message of a run.

    Args:
        page_id: The page id.
        n: The run number.
        runner: The runner name.
        model: The model name.
        changed: The files the run changed.

    Returns:
        ``[<page-id>] run <n> · <runner>/<model> · <changed files>``.
    """
    return f"[{page_id}] run {n} · {runner}/{model} · {_summary(changed)}"


def format_outcome(outcome: RunOutcome) -> str:
    """Returns the one-line summary printed after a run."""
    record = outcome.recorded.record
    estimate = (record.input or {}).get("total_est", 0)
    usage = record.usage
    parts = [
        f"run {record.n}",
        f"{record.runner}/{record.model}",
        f"{outcome.recorded.result.status}",
        f"input est {estimate:,} / actual {usage.input:,}"
        f" (cached {usage.cached:,})",
        f"output {usage.output:,}",
        f"changed {len(record.changed_files)}",
        f"unknown {len(record.unknown_files)}",
        f"issues {len(outcome.issues)}",
        f"commit {outcome.commit}",
        f"{outcome.recorded.result.duration:.1f}s",
    ]
    return " · ".join(parts)


def _summary(changed: list[str]) -> str:
    if not changed:
        return "no file changes"
    if len(changed) <= _SUMMARY_FILES:
        return ", ".join(changed)
    shown = changed[: _SUMMARY_FILES - 1]
    return f"{', '.join(shown)} +{len(changed) - len(shown)} more"


@contextmanager
def _environment(name: str, value: str) -> Iterator[None]:
    """Sets an environment variable for the agent process, then restores it."""
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def _snapshots(
    page_dir: Path, cwd: Path
) -> tuple[changes.Snapshot, changes.Snapshot | None]:
    repo = changes.take(cwd) if cwd != page_dir else None
    return changes.take(page_dir), repo


def _run_output(
    page_dir: Path,
    cwd: Path,
    before: tuple[changes.Snapshot, changes.Snapshot | None],
) -> tuple[list[str], list[str]]:
    """Returns the files a run changed and the new files it did not register.

    Page files are page-relative; code repository files carry ``repo:``.
    """
    page_before, repo_before = before
    page_after, repo_after = _snapshots(page_dir, cwd)
    changed = [
        p for p in page_after.changed_since(page_before) if not _bookkeeping(p)
    ]
    new = [
        p for p in page_after.new_untracked(page_before) if not _bookkeeping(p)
    ]
    if repo_before is not None and repo_after is not None:
        changed += [
            REPO_PREFIX + p for p in repo_after.changed_since(repo_before)
        ]
        new += [REPO_PREFIX + p for p in repo_after.new_untracked(repo_before)]
    registered = _artifacts(page_dir)
    managed = {STATE_FILE, "page.md"}
    unknown = [p for p in new if p not in registered and p not in managed]
    return changed, unknown


def _bookkeeping(path: str) -> bool:
    return path in _BOOKKEEPING or path.startswith(_BOOKKEEPING_DIRS)


def _artifacts(page_dir: Path) -> set[str]:
    try:
        header = pages.read_header(page_dir / STATE_FILE)
    except (OSError, frontmatter.FrontmatterError):
        return set()
    items = header.get("artifacts")
    return {str(a) for a in items} if isinstance(items, list) else set()


def _finish_record(
    page_dir: Path,
    recorded: RecordedRun,
    contract_version: str,
    output: tuple[list[str], list[str]],
    issues: list[Issue],
) -> None:
    """Adds what core learned after the run to ``runs/N.json``."""
    record, result = recorded.record, recorded.result
    record.changed_files, record.unknown_files = output
    record.contract = contract_version
    record.duration = result.duration
    record.error = result.error
    record.state_check = {
        "ok": not issues,
        "issues": [issue.to_dict() for issue in issues],
    }
    if result.status == "done":
        record.result_status = _state_status(page_dir)
    runs.write_run(page_dir, record)


def _state_status(page_dir: Path) -> str | None:
    try:
        status = pages.read_header(page_dir / STATE_FILE).get("status")
    except (OSError, frontmatter.FrontmatterError):
        return None
    return str(status) if status else None


def _commit_run(
    page_dir: Path, home: Path, recorded: RecordedRun, changed: list[str]
) -> str:
    record = recorded.record
    paths = [page_dir.relative_to(home).as_posix()]
    space = space_dir(page_dir)
    if space is not None and (space / SPACE_FILE).is_file():
        paths.append((space / SPACE_FILE).relative_to(home).as_posix())
    git.run(home, "add", "-A", "--", *paths)
    message = run_commit_message(
        page_dir.name,
        record.n,
        str(record.runner),
        str(record.model),
        changed,
    )
    git.commit(home, message, paths, unsigned=True)
    return git.head(home)


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code)


def _load(home: Path | None) -> config.Config:
    root = config.resolve_home(home)
    if not root.is_dir():
        raise _fail(f"app home {root} does not exist; run 'madang init' first")
    try:
        return config.load_config(root)
    except Exception as exc:
        raise _fail(f"cannot load config: {exc}") from exc


@app.command("run")
def run_command(
    page_id: Annotated[str, typer.Argument(help="Page id.")],
    request: Annotated[str, typer.Argument(help="What to do in this step.")],
    tool: Annotated[
        str, typer.Option("--tool", help="Runner: claude | codex.")
    ],
    model: Annotated[str, typer.Option("--model", help="Model name.")],
    effort: Annotated[
        str, typer.Option("--effort", help="Reasoning effort.")
    ] = "medium",
    target: Annotated[
        str | None,
        typer.Option("--target", help="Block the request is about, e.g. b05."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """Run one step of a page in a fresh session, then check and commit it."""
    cfg = _load(home)
    try:
        page_dir = pages.find_page(cfg.home, page_id)
        runner = make_runner(tool, cfg)
    except (pages.PageNotFoundError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    cwd = work_dir(page_dir)
    if not cwd.is_dir():
        raise _fail(f"working folder {cwd} does not exist")
    try:
        outcome = execute_run(
            page_dir,
            runner,
            cfg=cfg,
            model=model,
            effort=effort,
            request=request,
            target=target,
        )
    except (GitError, OSError, ValueError, frontmatter.FrontmatterError) as e:
        raise _fail(str(e)) from e
    for issue in outcome.issues:
        typer.echo(f"  {issue.format()}", err=True)
    if outcome.recorded.result.error:
        typer.echo(f"  {outcome.recorded.result.error}", err=True)
    typer.echo(format_outcome(outcome))
    if not outcome.ok:
        raise typer.Exit(1)


# page and space creation

page_app = typer.Typer(
    help="Create pages.", no_args_is_help=True, add_completion=False
)
space_app = typer.Typer(
    help="Create spaces.", no_args_is_help=True, add_completion=False
)
app.add_typer(page_app, name="page")
app.add_typer(space_app, name="space")


@page_app.command("new")
def page_new(
    title: Annotated[str, typer.Option("--title", help="Page title.")],
    space: Annotated[str, typer.Option("--space", help="Space slug.")] = "root",
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Page kind. Defaults to routes.yaml."),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option("--slug", help="Page slug. Defaults to the title."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """Create a page and print its id."""
    cfg = _load(home)
    kind = kind or cfg.routes.default_kind
    if kind not in cfg.routes.kinds:
        raise _fail(f"unknown kind '{kind}'; expected {cfg.routes.kinds}")
    try:
        page_dir = pages.create_page(
            cfg.home, space, title, slug=slug, kind=kind
        )
    except (FileNotFoundError, FileExistsError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(page_dir.name)


@space_app.command("new")
def space_new(
    slug: Annotated[str, typer.Argument(help="Space slug.")],
    title: Annotated[
        str | None, typer.Option("--title", help="Space title.")
    ] = None,
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="Code repository of the space."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """Create a space and print its slug."""
    cfg = _load(home)
    try:
        pages.create_space(cfg.home, slug, title=title, repo=repo)
    except (ValueError, FileExistsError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(slug)


cli_agent.register(app)


def main() -> None:
    """Runs the madang command line."""
    app()


if __name__ == "__main__":
    main()
