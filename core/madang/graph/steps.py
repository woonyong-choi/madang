"""페이지 실행 한 번을 이루는 단계: 조립, 실행, 기록, 검사, 답.

``madang run``과 흐름 그래프의 노드가 같은 단계를 공유한다. 단계 사이에서
넘기는 값은 실행 번호와 페이지 파일뿐이다. 프롬프트는 ``scratch/``에
남고, 실행 결과는 recorder가 page.md, ledger.md, ``runs/``에 쓴다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from madang import config, recorder
from madang.assemble import Assembled, assemble
from madang.cli_agent.context import BY_ENV
from madang.policy import with_rules
from madang.recorder.undo import REPO_PREFIX
from madang.runners.base import CliRunner, RunEvent
from madang.runners.record import RecordedRun, run_page
from madang.store import changes, frontmatter, pages, runs
from madang.store.log import read_messages
from madang.store.page import LEDGER_FILE, MADANG_DIR, project_root, work_dir
from madang.validate import Issue, validate_target

SCRATCH_DIR = pages.SCRATCH_DIR
# 코어가 직접 쓰는 페이지 파일. 실행 산출물로 보고하지 않는다.
_BOOKKEEPING = (f"{pages.BLOCKS_DIR}/{pages.LAST_BLOCK_FILE}",)
_BOOKKEEPING_DIRS = (f"{runs.RUNS_DIR}/", f"{SCRATCH_DIR}/")

Snapshots = tuple[changes.Snapshot, changes.Snapshot | None]


# 조립


def prompt_path(page_dir: Path, message: str) -> Path:
    """메시지의 최근 프롬프트 파일을 반환한다."""
    return page_dir / SCRATCH_DIR / f"{message}.prompt.md"


def _input_path(page_dir: Path, message: str) -> Path:
    return page_dir / SCRATCH_DIR / f"{message}.input.json"


def prepare(
    page_dir: Path,
    *,
    cfg: config.Config,
    runner: str,
    message: str,
    target: str | None,
    request: str,
    tier: int,
) -> Assembled:
    """프롬프트를 조립해 ``scratch/``에 저장한다.

    요청 끝에는 모든 실행 공통의 부작용 규칙이 붙는다.

    Args:
        page_dir: 페이지 폴더.
        cfg: 앱 홈 설정.
        runner: 러너 이름.
        message: 요청 메시지 블록 id. 파일 이름에 쓴다.
        target: 요청 대상 블록. 페이지 전체면 None.
        request: 이번 실행의 요청 본문.
        tier: 승격 단계.

    Returns:
        조립한 프롬프트와 그 추정.

    Raises:
        OSError: 페이지 파일을 읽거나 쓸 수 없는 경우.
        ValueError: 대상 블록에 파일이 없는 경우.
    """
    assembled = assemble(
        page_dir, target, with_rules(request), tier, cfg=cfg, runner=runner
    )
    path = prompt_path(page_dir, message)
    path.parent.mkdir(exist_ok=True)
    path.write_text(assembled.prompt, encoding="utf-8")
    meta = {"contract": assembled.contract, "input": assembled.estimate()}
    _input_path(page_dir, message).write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    return assembled


# 실행


def execute(
    page_dir: Path,
    runner: CliRunner,
    *,
    cfg: config.Config,
    message: str,
    route: dict[str, Any],
    trigger: dict[str, Any],
    on_event: Callable[[RunEvent], None] = lambda _event: None,
) -> RecordedRun:
    """저장된 프롬프트로 러너를 실행하고 바뀐 파일과 읽은 파일까지 기록한다.

    Args:
        page_dir: 페이지 폴더.
        runner: 사용할 러너.
        cfg: 앱 홈 설정.
        message: ``prepare``에 넘긴 메시지 블록 id.
        route: ``model``, ``effort``, ``kind``, ``tier``.
        trigger: 실행 기록의 ``trigger``.
        on_event: 러너 이벤트가 도착할 때마다 호출된다.

    Returns:
        끝난 실행. ``runs/N.json``에 이미 쓰여 있다.

    Raises:
        OSError: 저장된 프롬프트를 읽을 수 없는 경우.
    """
    prompt = prompt_path(page_dir, message).read_text(encoding="utf-8")
    meta = json.loads(_input_path(page_dir, message).read_text("utf-8"))
    cwd = work_dir(page_dir)
    before = snapshots(page_dir, cwd)
    with environment(BY_ENV, f"{runner.name}/{route['model']}"):
        recorded = run_page(
            runner,
            config=cfg,
            page_dir=page_dir,
            cwd=cwd,
            prompt=prompt,
            model=route["model"],
            effort=route["effort"],
            kind=route["kind"],
            tier=route["tier"],
            on_event=on_event,
            trigger=trigger,
            input=meta["input"],
        )
    record_output(
        page_dir, recorded, meta["contract"], run_output(page_dir, cwd, before)
    )
    recorder.set_reads(page_dir, recorded.n, recorded.result.read_files, cwd)
    return recorded


def reply(page_dir: Path, recorded: RecordedRun) -> str:
    """실행의 답을 에이전트 블록으로 page.md에 쌓는다.

    Returns:
        새 메시지 블록 id.
    """
    result = recorded.result
    answer = result.final_text if result.status == "done" else None
    return recorder.reply(
        page_dir,
        recorded.n,
        answer or f"{result.status}: {result.error or 'no answer'}",
    )


def message_text(page_dir: Path, block_id: str) -> str:
    """page.md에서 메시지 블록 하나의 본문을 반환한다.

    Args:
        page_dir: 페이지 폴더.
        block_id: 메시지 블록 id.

    Returns:
        머리 줄을 뺀 본문.

    Raises:
        KeyError: page.md에 그 블록이 없는 경우.
    """
    for message in read_messages(page_dir):
        if message.id == block_id:
            return message.text
    raise KeyError(f"message '{block_id}' is not in {pages.PAGE_FILE}")


# 기록과 검사


def check(page_dir: Path, cfg: config.Config, n: int) -> list[Issue]:
    """실행 뒤 페이지를 검사하고 결과를 ``runs/N.json``에 더한다.

    Args:
        page_dir: 페이지 폴더.
        cfg: 앱 홈 설정.
        n: 실행 번호.

    Returns:
        찾은 문제.
    """
    issues = validate_target(
        page_dir,
        repo=project_root(page_dir),
        token_limit=cfg.madang.limits.ledger_tokens,
        kinds=cfg.routes.kinds,
    )
    record = runs.read_run(page_dir, n)
    record.state_check = {
        "ok": not issues,
        "issues": [issue.to_dict() for issue in issues],
    }
    recorder.save_run(page_dir, record)
    return issues


def record_output(
    page_dir: Path,
    recorded: RecordedRun,
    contract_version: str,
    output: tuple[list[str], list[str]],
) -> None:
    """실행 뒤 코어가 알게 된 내용을 ``runs/N.json``에 더한다."""
    record, result = recorded.record, recorded.result
    record.changed_files, record.unknown_files = output
    record.contract = contract_version
    record.duration = result.duration
    record.error = result.error
    if result.status == "done":
        record.result_status = state_status(page_dir)
    recorder.save_run(page_dir, record)


def state_status(page_dir: Path) -> str | None:
    """ledger.md 머리부의 status를 반환한다. 읽을 수 없으면 None."""
    try:
        status = pages.read_header(page_dir / LEDGER_FILE).get("status")
    except (OSError, frontmatter.FrontmatterError):
        return None
    return str(status) if status else None


def snapshots(page_dir: Path, cwd: Path) -> Snapshots:
    """페이지 폴더와(다르면) 작업 폴더의 변경 스냅샷을 찍는다.

    페이지 폴더는 대개 git에서 빠져 있으므로 파일 목록으로 찍는다. 작업
    폴더(프로젝트)는 ``.madang/``을 뺀 변경을 찍는다.
    """
    repo = changes.take(cwd, exclude=(MADANG_DIR,)) if cwd != page_dir else None
    return changes.listing(page_dir), repo


def run_output(
    page_dir: Path, cwd: Path, before: Snapshots
) -> tuple[list[str], list[str]]:
    """실행이 바꾼 파일과 등록하지 않은 새 파일을 반환한다.

    페이지 파일은 페이지 기준 상대 경로이고, 프로젝트 폴더의 파일에는
    ``repo:`` 접두가 붙는다.
    """
    page_before, repo_before = before
    page_after, repo_after = snapshots(page_dir, cwd)
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
    managed = {LEDGER_FILE, pages.PAGE_FILE}
    unknown = [p for p in new if p not in registered and p not in managed]
    return changed, unknown


def _bookkeeping(path: str) -> bool:
    return path in _BOOKKEEPING or path.startswith(_BOOKKEEPING_DIRS)


def _artifacts(page_dir: Path) -> set[str]:
    try:
        header = pages.read_header(page_dir / LEDGER_FILE)
    except (OSError, frontmatter.FrontmatterError):
        return set()
    items = header.get("artifacts")
    if not isinstance(items, list):
        return set()
    # 실행물은 {path, run, name, command} 매핑으로 등록된다.
    return {
        str(item.get("path") if isinstance(item, dict) else item)
        for item in items
    }


# 환경


@contextmanager
def environment(name: str, value: str) -> Iterator[None]:
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
