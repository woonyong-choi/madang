"""``madang artifact add``: 페이지가 만든 파일을 ledger.md에 등록한다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from madang.cli_agent.context import AgentError, PageContext, guarded
from madang.cli_agent.items import items_of
from madang.store import pages
from madang.store.page import LEDGER_FILE

REPO_PREFIX = "repo:"


def _within(path: Path, base: Path) -> str | None:
    try:
        return path.relative_to(base.resolve()).as_posix()
    except ValueError:
        return None


def _relative(raw: str) -> str:
    path = Path(raw)
    if ".." in path.parts:
        raise AgentError(f"{raw}에는 상위 폴더('..')를 쓸 수 없다")
    return path.as_posix()


def artifact_entry(ctx: PageContext, raw: str) -> str:
    """경로를 ledger.md 산출물 항목으로 정규화한다.

    Args:
        ctx: 산출물이 속한 페이지.
        raw: 페이지 기준 상대 경로, 절대 경로, 또는 ``repo:<path>``
            (프로젝트 폴더 기준).

    Returns:
        ``blocks/...``(페이지 기준) 또는 ``repo:<path>``.

    Raises:
        AgentError: 경로에 ``..``가 있거나 페이지와 프로젝트 폴더 밖에 있다.
    """
    if raw.startswith(REPO_PREFIX):
        return REPO_PREFIX + _relative(raw[len(REPO_PREFIX) :])
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return _relative(raw)
    path = path.resolve()
    if (rel := _within(path, ctx.page_dir)) is not None:
        return rel
    repo = ctx.repo()
    if repo is not None and (rel := _within(path, repo)) is not None:
        return REPO_PREFIX + rel
    raise AgentError(f"{raw}는 페이지 폴더와 프로젝트 폴더 밖에 있다")


def register(header: dict[str, Any], entry: str) -> bool:
    """머리부의 ``artifacts``에 ``entry``를 더한다.

    Args:
        header: ledger.md 머리부.
        entry: 산출물 항목.

    Returns:
        새로 더했으면 True, 이미 있었으면 False.
    """
    artifacts = items_of(header, "artifacts")
    if entry in artifacts:
        return False
    artifacts.append(entry)
    header["artifacts"] = artifacts
    return True


def add_artifact(ctx: PageContext, raw: str) -> None:
    """파일을 ledger.md의 산출물로 등록한다.

    Args:
        ctx: 변경할 페이지.
        raw: 파일. ``artifact_entry``가 받는 형식.

    Raises:
        AgentError: 허용되지 않는 경로이거나 페이지 검증에 실패했다.
    """
    entry = artifact_entry(ctx, raw)
    with guarded(ctx, ctx.page_dir / LEDGER_FILE):
        pages.update_state(ctx.page_dir, lambda header: register(header, entry))
