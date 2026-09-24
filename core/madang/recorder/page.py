"""page.md 쓰기: 요청 블록, 실행 결과 블록, 묻는 블록과 그 답."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from madang.recorder import undo
from madang.store.log import append_message

USER = "user"
ROUTER = "router"
AGENT = "agent"
ASK_KEY = "ask"


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


def ask(
    page_dir: Path,
    n: int,
    question: str,
    reasons: Sequence[str],
    options: Sequence[str],
    *,
    output: Sequence[str] = (),
) -> str:
    """정책이 멈춘 이유와 선택지를 묻는 블록으로 page.md에 쌓는다.

    사람은 이 블록에서만 답한다. 블록 머리에 ``ask=true``와 선택지가
    남는다.

    Args:
        page_dir: 페이지 폴더.
        n: 멈춘 흐름의 마지막 실행 번호.
        question: 묻는 말.
        reasons: 정책이 거부한 이유.
        options: 고를 수 있는 답.
        output: 이유를 보여 주는 명령 출력(테스트 출력의 끝 줄 등).

    Returns:
        새 블록 id.
    """
    lines = [question, "", *(f"- {reason}" for reason in reasons)]
    if output:
        lines += ["", "```text", *output, "```"]
    lines += ["", "선택지: " + " | ".join(options)]
    attrs = {"run": n, ASK_KEY: "true", "options": ",".join(options)}
    block_id = append_message(page_dir, ROUTER, "\n".join(lines), attrs)
    undo.track(page_dir, n)
    return block_id


def answer(page_dir: Path, n: int, block: str, choice: str) -> str:
    """묻는 블록 ``block``에 사람이 고른 답을 page.md에 쌓는다.

    Args:
        page_dir: 페이지 폴더.
        n: 묻는 블록의 실행 번호.
        block: 묻는 블록 id.
        choice: 고른 답.

    Returns:
        새 블록 id.
    """
    block_id = append_message(page_dir, USER, choice, {"answer": block})
    undo.track(page_dir, n)
    return block_id
