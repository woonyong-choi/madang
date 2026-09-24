"""페이지에 대해 러너를 실행하고 실행 기록과 원본 스트림을 남긴다.

요약은 ``runs/N.json``, 원본 스트림은 ``runs/N.jsonl``이다. 둘 다
recorder가 번호를 내주고 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from madang import recorder
from madang.config import Config, ConfigError
from madang.policy import Policy
from madang.runners.base import CliRunner, RunEvent, RunResult
from madang.store import runs
from madang.store.page import project_root, records_dir


@dataclass
class RecordedRun:
    """끝난 실행과 그 기록이 쓰인 위치.

    Attributes:
        n: 실행 번호.
        result: 러너 결과.
        record: ``runs/N.json``에 쓴 기록.
        path: 그 기록의 경로.
    """

    n: int
    result: RunResult
    record: runs.RunRecord
    path: Path


def timeout_seconds(config: Config, kind: str) -> float | None:
    """``kind``의 실행 타임아웃을 반환한다.

    Args:
        config: The loaded app home configuration.
        kind: 실행 종류.

    Returns:
        ``limits.run_timeout_minutes[kind]``를 초로 환산한 값. 없으면 None.
    """
    minutes = config.madang.limits.run_timeout_minutes.get(kind)
    return float(minutes) * 60 if minutes else None


def run_page(
    runner: CliRunner,
    *,
    config: Config,
    page_dir: Path,
    cwd: Path,
    prompt: str,
    model: str,
    effort: str,
    kind: str,
    on_event: Callable[[RunEvent], None] = lambda _event: None,
    tier: int | None = None,
    trigger: dict[str, Any] | None = None,
    input: dict[str, Any] | None = None,
) -> RecordedRun:
    """다음 실행 번호를 할당해 실행하고 실행 기록을 쓴다.

    페이지 id(폴더 이름)는 ``MADANG_PAGE``로 에이전트에 전달한다. 러너
    인자의 ``{records}``는 프로젝트 기록 폴더이고, 프로젝트 정책의 금지
    명령은 러너 인자로 더한다.

    Args:
        runner: 사용할 러너.
        config: The loaded app home configuration.
        page_dir: 페이지 폴더.
        cwd: 실행의 작업 디렉터리.
        prompt: 프롬프트.
        model: 모델 이름.
        effort: 추론 강도.
        kind: 실행 종류. 타임아웃을 고른다.
        on_event: 이벤트가 도착할 때마다 호출된다.
        tier: 라우팅 티어. 없을 수 있다.
        trigger: 실행을 시작한 요인. 기록하는 경우.
        input: 실행 입력. 기록하는 경우.

    Returns:
        끝난 실행.
    """
    n = recorder.begin(page_dir)
    started = datetime.now().astimezone()
    result = runner.exec(
        cwd=cwd,
        prompt=prompt,
        model=model,
        effort=effort,
        on_event=on_event,
        page=page_dir.name,
        records=records_dir(page_dir),
        extra_args=deny_args(runner.name, page_dir),
        timeout=timeout_seconds(config, kind),
        events_log=runs.events_path(page_dir, n),
    )
    record = runs.RunRecord(
        n=n,
        started=started,
        finished=datetime.now().astimezone(),
        trigger=trigger,
        kind=kind,
        tier=tier,
        runner=runner.name,
        model=model,
        effort=effort,
        input=input,
        usage=runs.RunUsage(
            input=result.usage.input,
            cached=result.usage.cached,
            output=result.usage.output,
        ),
        changed_files=[
            _relative(p, page_dir, cwd) for p in result.changed_files
        ],
        result_status=result.status,
        events_log=runs.events_rel(n),
    )
    path = recorder.save_run(page_dir, record)
    return RecordedRun(n=n, result=result, record=record, path=path)


def deny_args(runner: str, page_dir: Path) -> list[str]:
    """페이지가 속한 프로젝트 정책의 ``deny``를 막는 러너 인자.

    프로젝트 설정을 읽지 못하면 기본 금지 목록으로 막는다.

    Args:
        runner: 러너 이름.
        page_dir: 페이지 폴더.

    Returns:
        명령줄에 더할 인자. 러너가 금지 규칙을 받지 못하면 빈 목록.
    """
    root = project_root(page_dir)
    try:
        policy = Policy() if root is None else Policy.load(root)
    except (OSError, ConfigError):
        policy = Policy()
    return policy.runner_args(runner)


def _relative(path: str, page_dir: Path, cwd: Path) -> str:
    """페이지 안이면 페이지 기준, 아니면 cwd 기준, 아니면 받은 그대로."""
    p = Path(path)
    if not p.is_absolute():
        p = cwd / p
    p = p.resolve()
    for base in (page_dir, cwd):
        try:
            return p.relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return path
