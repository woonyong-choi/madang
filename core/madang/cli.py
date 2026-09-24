"""madang 명령줄 진입점."""

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
    help="Madang 코어 명령줄.",
    no_args_is_help=True,
    add_completion=False,
)

HomeOption = Annotated[
    Path | None,
    typer.Option(
        "--home",
        help="앱 홈 폴더. 기본값은 $MADANG_HOME 또는 ~/.madang.",
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
            help="버전을 출력하고 종료한다.",
        ),
    ] = False,
) -> None:
    """Madang 코어 명령줄."""


@app.command()
def init(home: HomeOption = None) -> None:
    """앱 홈(설정, 루트 메모리, 루트 스페이스, git 저장소)을 만든다."""
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
        Path, typer.Argument(help="state.md 경로 또는 페이지 폴더.")
    ],
    repo: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            help=("repo: 산출물의 코드 저장소. 기본값은 space.md의 repo."),
        ),
    ] = None,
    home: HomeOption = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="문제 목록을 JSON으로 출력한다.")
    ] = False,
) -> None:
    """페이지의 state.md(와 page.md)를 검사한다. 문제가 있으면 1로 종료한다."""
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


# 단일 실행

SCRATCH_DIR = "scratch"
REPO_PREFIX = "repo:"
# 코어가 직접 쓰는 페이지 파일. 실행 산출물로 보고하지 않는다.
_BOOKKEEPING = (pages.LOG_FILE, f"{pages.BLOCKS_DIR}/{pages.LAST_BLOCK_FILE}")
_BOOKKEEPING_DIRS = (f"{runs.RUNS_DIR}/", f"{SCRATCH_DIR}/")
_SUMMARY_FILES = 3


@dataclass
class RunOutcome:
    """페이지의 끝난 단일 실행.

    Attributes:
        recorded: 실행과 그 기록.
        issues: 실행 뒤 상태 검사에서 찾은 문제.
        commit: 앱 홈 커밋의 짧은 해시.
    """

    recorded: RecordedRun
    issues: list[Issue]
    commit: str

    @property
    def ok(self) -> bool:
        """러너가 끝났고 페이지가 검사를 통과했는지 여부."""
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
    """새 세션에서 페이지의 한 단계를 실행하고 결과를 커밋한다.

    요청을 기록하고, 프롬프트를 조립해 ``scratch/``에 저장한다. 러너는
    스페이스의 코드 저장소(없으면 페이지 폴더)에서 작업한다. 이후 페이지를
    검사하고, 실행을 기록하고, 답을 기록한 뒤 앱 홈을 커밋한다.

    Args:
        page_dir: 페이지 폴더.
        runner: 사용할 러너.
        cfg: 앱 홈 설정.
        model: 모델 이름.
        effort: 추론 강도.
        request: 메시지 본문.
        target: 요청 대상 블록. 페이지 전체면 None.

    Returns:
        끝난 실행.

    Raises:
        GitError: 앱 홈 커밋이 실패한 경우.
        OSError: 페이지 파일을 읽거나 쓸 수 없는 경우.
        ValueError: 대상 블록에 파일이 없는 경우.
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
    """실행의 앱 홈 커밋 메시지를 반환한다.

    Args:
        page_id: 페이지 id.
        n: 실행 번호.
        runner: 러너 이름.
        model: 모델 이름.
        changed: 실행이 바꾼 파일.

    Returns:
        ``[<page-id>] run <n> · <runner>/<model> · <changed files>``.
    """
    return f"[{page_id}] run {n} · {runner}/{model} · {_summary(changed)}"


def format_outcome(outcome: RunOutcome) -> str:
    """실행 뒤 출력하는 한 줄 요약을 반환한다."""
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
    """에이전트 프로세스용 환경 변수를 설정하고 끝나면 되돌린다."""
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
    """실행이 바꾼 파일과 등록하지 않은 새 파일을 반환한다.

    페이지 파일은 페이지 기준 상대 경로이고, 코드 저장소 파일에는
    ``repo:`` 접두가 붙는다.
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
    """실행 뒤 코어가 알게 된 내용을 ``runs/N.json``에 더한다."""
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
    page_id: Annotated[str, typer.Argument(help="페이지 id.")],
    request: Annotated[str, typer.Argument(help="이 단계에서 할 일.")],
    tool: Annotated[str, typer.Option("--tool", help="러너: claude | codex.")],
    model: Annotated[str, typer.Option("--model", help="모델 이름.")],
    effort: Annotated[
        str, typer.Option("--effort", help="추론 강도.")
    ] = "medium",
    target: Annotated[
        str | None,
        typer.Option("--target", help="요청 대상 블록. 예: b05."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """새 세션에서 페이지의 한 단계를 실행한 뒤 검사하고 커밋한다."""
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


# 페이지와 스페이스 생성

page_app = typer.Typer(
    help="페이지를 만든다.", no_args_is_help=True, add_completion=False
)
space_app = typer.Typer(
    help="스페이스를 만든다.", no_args_is_help=True, add_completion=False
)
app.add_typer(page_app, name="page")
app.add_typer(space_app, name="space")


@page_app.command("new")
def page_new(
    title: Annotated[str, typer.Option("--title", help="페이지 제목.")],
    space: Annotated[
        str, typer.Option("--space", help="스페이스 슬러그.")
    ] = "root",
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="페이지 종류. 기본값은 routes.yaml."),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option("--slug", help="페이지 슬러그. 기본값은 제목."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """페이지를 만들고 id를 출력한다."""
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
    slug: Annotated[str, typer.Argument(help="스페이스 슬러그.")],
    title: Annotated[
        str | None, typer.Option("--title", help="스페이스 제목.")
    ] = None,
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="스페이스의 코드 저장소."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """스페이스를 만들고 슬러그를 출력한다."""
    cfg = _load(home)
    try:
        pages.create_space(cfg.home, slug, title=title, repo=repo)
    except (ValueError, FileExistsError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(slug)


cli_agent.register(app)


def main() -> None:
    """Madang 명령줄을 실행한다."""
    app()


if __name__ == "__main__":
    main()
