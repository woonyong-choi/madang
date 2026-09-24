"""page.md 쓰기: 요청 블록과 실행 결과 블록."""

from __future__ import annotations

from pathlib import Path

from madang.recorder import undo
from madang.store.log import append_message

USER = "user"
AGENT = "agent"


def request(page_dir: Path, text: str, target: str | None) -> str:
    """사용자 요청을 page.md에 블록으로 쌓는다.

    Args:
        page_dir: 페이지 폴더.
        text: 요청 본문.
        target: 요청 대상 블록 id. 페이지 전체면 None.

    Returns:
        새 블록 id.
    """
    return append_message(page_dir, USER, text, {"target": target or "page"})


def reply(page_dir: Path, n: int, text: str) -> str:
    """실행 ``n``의 결과를 에이전트 블록으로 page.md에 쌓는다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호. 블록 머리에 ``run=n``으로 남는다.
        text: 결과 본문.

    Returns:
        새 블록 id.
    """
    block_id = append_message(page_dir, AGENT, text, {"run": n})
    undo.track(page_dir, n)
    return block_id
