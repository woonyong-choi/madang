"""페이지에 대해 러너를 실행하고 실행 기록과 이벤트 로그를 남긴다.

기록은 ``runs/N.json``, 로그는 ``runs/N.events.jsonl``이다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from madang.config import Config
from madang.runners.base import CliRunner, RunEvent, RunResult
from madang.store import runs


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

    페이지 id(폴더 이름)는 ``MADANG_PAGE``로 에이전트에 전달한다.

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
    n = runs.allocate(page_dir)
    started = datetime.now().astimezone()
    result = runner.exec(
        cwd=cwd,
        prompt=prompt,
        model=model,
        effort=effort,
        on_event=on_event,
        page=page_dir.name,
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
    path = runs.write_run(page_dir, record)
    return RecordedRun(n=n, result=result, record=record, path=path)


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
