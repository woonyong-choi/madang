"""실행 기록 쓰기: 번호 예약과 ``runs/N.json`` 요약."""

from __future__ import annotations

from pathlib import Path

from madang.recorder import undo
from madang.store import runs


def begin(page_dir: Path) -> int:
    """다음 실행 번호를 예약하고 실행 전 페이지 파일을 스냅샷으로 남긴다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        새 실행 번호. 빈 ``runs/N.jsonl``이 이미 있다.
    """
    n = runs.allocate(page_dir)
    undo.open_log(page_dir, n)
    return n


def save_run(page_dir: Path, record: runs.RunRecord) -> Path:
    """실행 요약을 ``runs/N.json``에 쓰고 그 실행의 부작용을 다시 적는다.

    Args:
        page_dir: 페이지 폴더.
        record: 실행 요약.

    Returns:
        쓴 경로.
    """
    path = runs.write_run(page_dir, record)
    undo.track(page_dir, record.n)
    return path
