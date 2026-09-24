"""madang 명령줄 진입점."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from madang import __version__, cli_agent, config
from madang.graph import Flow, FlowResult, events, steps
from madang.runners import make_runner
from madang.runners.base import CliRunner
from madang.runners.record import RecordedRun
from madang.store import frontmatter, pages, projects
from madang.store.home import (
    NotAHomeError,
    check_layout,
    init_home,
    is_initialized,
)
from madang.store.log import append_message
from madang.store.page import LEDGER_FILE, work_dir
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
    """앱 홈(전역 설정과 Profile)을 만든다. 페이지는 프로젝트에 둔다."""
    path = config.resolve_home(home)
    try:
        result = init_home(path)
    except (NotAHomeError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if result.created:
        typer.echo(f"initialized {path} ({len(result.created)} files)")
    else:
        typer.echo(f"already initialized: {path}")


@app.command()
def validate(
    target: Annotated[
        Path, typer.Argument(help="ledger.md 경로 또는 페이지 폴더.")
    ],
    repo: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            help=("repo: 산출물의 기준 폴더. 기본값은 페이지가 속한 프로젝트."),
        ),
    ] = None,
    home: HomeOption = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="문제 목록을 JSON으로 출력한다.")
    ] = False,
) -> None:
    """페이지의 ledger.md(와 page.md)를 검사한다. 문제가 있으면 1로 종료한다."""
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
        token_limit=cfg.madang.limits.ledger_tokens,
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


@dataclass
class RunOutcome:
    """페이지의 끝난 단일 실행.

    Attributes:
        recorded: 실행과 그 기록.
        issues: 실행 뒤 상태 검사에서 찾은 문제.
    """

    recorded: RecordedRun
    issues: list[Issue]

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
    """새 세션에서 페이지의 한 단계를 실행한다.

    요청을 기록하고, 프롬프트를 조립해 ``scratch/``에 저장한다. 러너는
    페이지가 속한 프로젝트 폴더에서 작업한다. 이후 페이지를 검사하고,
    실행을 기록하고, 답을 기록한다.

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
        OSError: 페이지 파일을 읽거나 쓸 수 없는 경우.
        ValueError: 대상 블록에 파일이 없는 경우.
    """
    state = pages.read_header(page_dir / LEDGER_FILE)
    tier = int(state.get("tier") or 1)
    kind = str(state.get("kind") or cfg.routes.default_kind)
    if target is not None and not pages.block_files(page_dir, target):
        raise ValueError(f"block '{target}' has no file in blocks/")

    message = append_message(
        page_dir, "user", request, {"target": target or "page"}
    )
    steps.prepare(
        page_dir,
        cfg=cfg,
        runner=runner.name,
        message=message,
        target=target,
        request=request,
        tier=tier,
    )
    recorded = steps.execute(
        page_dir,
        runner,
        cfg=cfg,
        message=message,
        route={"model": model, "effort": effort, "kind": kind, "tier": tier},
        trigger={"message": message, "target": target or "page"},
    )
    issues = steps.check(page_dir, cfg, recorded.n)
    steps.reply(page_dir, recorded)
    return RunOutcome(recorded=recorded, issues=issues)


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
        f"{outcome.recorded.result.duration:.1f}s",
    ]
    return " · ".join(parts)


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code)


def _load(home: Path | None) -> config.Config:
    root = config.resolve_home(home)
    if not root.is_dir():
        raise _fail(f"app home {root} does not exist; run 'madang init' first")
    try:
        check_layout(root)
    except NotAHomeError as exc:
        raise _fail(str(exc)) from exc
    try:
        return config.load_config(root)
    except Exception as exc:
        raise _fail(f"cannot load config: {exc}") from exc


@app.command("run")
def run_command(
    page_id: Annotated[str, typer.Argument(help="페이지 id.")],
    request: Annotated[str, typer.Argument(help="이 단계에서 할 일.")],
    tool: Annotated[
        str | None, typer.Option("--tool", help="러너: claude | codex.")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="모델 이름.")
    ] = None,
    effort: Annotated[
        str, typer.Option("--effort", help="추론 강도.")
    ] = "medium",
    target: Annotated[
        str | None,
        typer.Option("--target", help="요청 대상 블록. 예: b05."),
    ] = None,
    flow: Annotated[
        bool,
        typer.Option(
            "--flow",
            help=(
                "흐름 그래프로 처리한다. 종류·러너·모델은 config.yaml의 "
                "routes 절이 고르고, 검사·리뷰·승격까지 이어 간다."
            ),
        ),
    ] = False,
    home: HomeOption = None,
) -> None:
    """새 세션에서 페이지의 한 단계를 실행한 뒤 검사한다.

    --flow를 주면 메시지 하나를 흐름 그래프로 끝까지 처리한다.
    """
    cfg = _load(home)
    if flow:
        if tool or model:
            raise _fail("--tool and --model cannot be used with --flow")
        _run_flow(cfg, page_id, request, target)
        return
    if not tool or not model:
        raise _fail("--tool and --model are required without --flow")
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
    except (OSError, ValueError, frontmatter.FrontmatterError) as e:
        raise _fail(str(e)) from e
    for issue in outcome.issues:
        typer.echo(f"  {issue.format()}", err=True)
    if outcome.recorded.result.error:
        typer.echo(f"  {outcome.recorded.result.error}", err=True)
    typer.echo(format_outcome(outcome))
    if not outcome.ok:
        raise typer.Exit(1)


@app.command("resume")
def resume_command(
    thread_id: Annotated[
        str, typer.Argument(help="멈춘 흐름 id. 예: <page-id>/b01.")
    ],
    choice: Annotated[str, typer.Argument(help="선택지 중 하나.")],
    home: HomeOption = None,
) -> None:
    """사람의 답을 기다리는 흐름에 답을 주고 이어 간다."""
    cfg = _load(home)
    try:
        result = Flow(cfg, on_event=_echo_event).resume(thread_id, choice)
    except (OSError, ValueError, frontmatter.FrontmatterError) as e:
        raise _fail(str(e)) from e
    _finish_flow(result)


def format_flow(result: FlowResult) -> str:
    """흐름이 끝나거나 멈춘 뒤 출력하는 한 줄 요약을 반환한다."""
    state = result.state
    parts = [
        f"flow {result.thread_id}",
        f"kind {state['kind'] or '-'}",
        f"runs {state['runs_this_message']}",
        f"last run {state['run_n'] or '-'}",
    ]
    if result.waiting is not None:
        options = "|".join(result.waiting["options"])
        parts += [f"waiting {result.waiting['reason']}", f"options {options}"]
    else:
        parts.append(state["result_status"] or "-")
    return " · ".join(parts)


def _run_flow(
    cfg: config.Config, page_id: str, request: str, target: str | None
) -> None:
    flow = Flow(cfg, on_event=_echo_event)
    try:
        result = flow.start(page_id, request, {"block": target})
    except (
        pages.PageNotFoundError,
        OSError,
        ValueError,
        frontmatter.FrontmatterError,
    ) as exc:
        raise _fail(str(exc)) from exc
    _finish_flow(result)


def _finish_flow(result: FlowResult) -> None:
    typer.echo(format_flow(result))
    stopped = result.state["result_status"] in ("blocked", "cancelled")
    if result.waiting is not None or stopped:
        raise typer.Exit(1)


_ECHOED = (
    events.RUN_STARTED,
    events.RUN_FINISHED,
    events.RUN_FAILED,
    events.FLOW_WAITING,
    events.PAGE_UNKNOWN_FILES,
)


def _echo_event(name: str, payload: dict[str, Any]) -> None:
    """흐름 이벤트 중 사람이 볼 것만 표준 오류에 한 줄로 쓴다."""
    if name not in _ECHOED:
        return
    shown = {k: v for k, v in payload.items() if k not in ("page", "message")}
    typer.echo(f"{name} {json.dumps(shown, ensure_ascii=False)}", err=True)


# core API


@app.command()
def serve(
    home: HomeOption = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            help=(
                "처음 시도할 포트. 쓰이고 있으면 다음 포트를 쓴다. "
                "기본값은 config.yaml의 core.port(7470)."
            ),
        ),
    ] = None,
) -> None:
    """Core API를 127.0.0.1에 띄운다. 고른 포트는 <home>/core.port에 적는다."""
    from madang.api.server import serve as run_server

    root = config.resolve_home(home)
    start = port
    if start is None:
        try:
            start = config.load_config(root).madang.core.port
        except Exception:
            start = config.CoreSettings().port
    try:
        run_server(root, start)
    except OSError as exc:
        raise _fail(str(exc)) from exc


@app.command()
def openapi() -> None:
    """Core API 계약(OpenAPI YAML)을 출력한다. 서버가 돌려주는 문서와 같다."""
    import sys

    from madang.api.contract import contract_text

    sys.stdout.write(contract_text())


# 프로젝트와 페이지

project_app = typer.Typer(
    help="프로젝트(페이지 기록을 .madang/에 담는 폴더)를 관리한다.",
    no_args_is_help=True,
    add_completion=False,
)
page_app = typer.Typer(
    help="페이지를 만든다.", no_args_is_help=True, add_completion=False
)
app.add_typer(project_app, name="project")
app.add_typer(page_app, name="page")


@project_app.command("add")
def project_add(
    path: Annotated[Path, typer.Argument(help="프로젝트 폴더.")],
    project_id: Annotated[
        str | None,
        typer.Option("--id", help="프로젝트 id. 기본값은 폴더 이름."),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="프로젝트 제목. 기본값은 폴더 이름."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """폴더에 .madang/을 만들고 프로젝트로 등록한 뒤 id를 출력한다."""
    cfg = _load(home)
    if not is_initialized(cfg.home):
        raise _fail(f"app home {cfg.home} has no settings; run 'madang init'")
    try:
        project = projects.add(
            cfg.home, path, project_id=project_id, title=title
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(project.id)


@project_app.command("list")
def project_list(home: HomeOption = None) -> None:
    """등록한 프로젝트를 한 줄에 하나씩(id, 폴더) 출력한다."""
    cfg = _load(home)
    for project in projects.load(cfg.home):
        typer.echo(f"{project.id}\t{project.root}")


@page_app.command("new")
def page_new(
    title: Annotated[str, typer.Option("--title", help="페이지 제목.")],
    project: Annotated[str, typer.Option("--project", help="프로젝트 id.")],
    kind: Annotated[
        str | None,
        typer.Option(
            "--kind", help="페이지 종류. 기본값은 config.yaml의 routes 절."
        ),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option("--slug", help="페이지 슬러그. 기본값은 제목."),
    ] = None,
    home: HomeOption = None,
) -> None:
    """프로젝트의 .madang/pages/에 페이지를 만들고 id를 출력한다."""
    cfg = _load(home)
    kind = kind or cfg.routes.default_kind
    if kind not in cfg.routes.kinds:
        raise _fail(f"unknown kind '{kind}'; expected {cfg.routes.kinds}")
    try:
        found = projects.get(cfg.home, project)
        page_dir = pages.create_page(
            found.pages_dir, title, slug=slug, kind=kind
        )
    except (FileNotFoundError, FileExistsError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(page_dir.name)


cli_agent.register(app)


def main() -> None:
    """Madang 명령줄을 실행한다."""
    app()


if __name__ == "__main__":
    main()
