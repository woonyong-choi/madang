"""ledger.md 머리부 쓰기: 상태, 라우팅 표시, 산출물, 읽은 파일.

실행에 딸린 쓰기는 실행 번호를 받아 그 실행의 부작용으로 남긴다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from madang.recorder import undo
from madang.store import pages

READS_KEY = "reads"
ARTIFACTS_KEY = "artifacts"


def set_status(page_dir: Path, status: str, n: int | None = None) -> None:
    """ledger.md ``status``를 바꾼다.

    Args:
        page_dir: 페이지 폴더.
        status: 새 상태.
        n: 이 변경을 부른 실행 번호. 없으면 None.
    """
    _update(page_dir, lambda header: header.update(status=status), n)


def mark_route(
    page_dir: Path,
    *,
    tier: int,
    attempts: int,
    owner: str | None,
    n: int | None = None,
) -> None:
    """다음 실행의 승격 단계와 시도 횟수, 구현자를 남긴다.

    Args:
        page_dir: 페이지 폴더.
        tier: 승격 단계.
        attempts: 이 단계의 시도 횟수.
        owner: ``runner/model``. 리뷰처럼 구현자가 바뀌지 않으면 None.
        n: 이 표시를 부른 직전 실행 번호. 메시지의 첫 실행이면 None.
    """

    def mark(header: dict[str, Any]) -> None:
        header["tier"] = tier
        header["attempts"] = attempts
        if owner is not None:
            header["owner"] = owner

    _update(page_dir, mark, n)


def set_reads(page_dir: Path, n: int, paths: Sequence[str], cwd: Path) -> None:
    """실행 ``n``이 읽은 파일로 ledger.md ``reads``를 바꾼다.

    ``artifacts``와 같은 규칙으로 적는다. 페이지 파일은 페이지 기준,
    작업 폴더 파일은 ``repo:`` 접두, 그 밖은 받은 그대로다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호.
        paths: 러너가 알려 준 경로. 상대 경로는 ``cwd`` 기준이다.
        cwd: 실행의 작업 폴더.
    """
    reads = list(dict.fromkeys(_entry(p, page_dir, cwd) for p in paths))
    _update(page_dir, lambda header: header.update({READS_KEY: reads}), n)


def add_artifact(page_dir: Path, entry: str) -> None:
    """ledger.md ``artifacts``에 ``entry``가 없으면 더한다."""

    def append(header: dict[str, Any]) -> None:
        items = header.get(ARTIFACTS_KEY)
        items = list(items) if isinstance(items, list) else []
        if entry not in items:
            items.append(entry)
        header[ARTIFACTS_KEY] = items

    _update(page_dir, append, None)


def _entry(path: str, page_dir: Path, cwd: Path) -> str:
    target = (cwd / path).resolve()
    for base, prefix in ((page_dir, ""), (cwd, undo.REPO_PREFIX)):
        if target.is_relative_to(base.resolve()):
            return prefix + target.relative_to(base.resolve()).as_posix()
    return path


def _update(
    page_dir: Path,
    mutate: Callable[[dict[str, Any]], None],
    n: int | None,
) -> None:
    pages.update_state(page_dir, mutate)
    if n is not None:
        undo.track(page_dir, n)
