"""페이지 대화: ``log.md``에 덧붙이는 메시지 블록.

각 블록은 한 줄 주석 머리
``<!-- bNN | <time> | <role> | key=value ... -->``로 시작하고 본문이 따른다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from madang.store import pages


def format_header(
    block_id: str, stamp: str, role: str, attrs: Mapping[str, object]
) -> str:
    """메시지 블록을 여는 주석 줄을 반환한다.

    Args:
        block_id: 블록 id.
        stamp: 메시지의 ISO 8601 시각.
        role: 작성자: user, router, agent 중 하나.
        attrs: 추가 ``key=value`` 필드(순서 유지).

    Returns:
        끝 줄바꿈이 없는 머리 줄.
    """
    fields = " ".join(f"{key}={value}" for key, value in attrs.items())
    head = f"<!-- {block_id} | {stamp} | {role}"
    return f"{head} | {fields} -->" if fields else f"{head} -->"


def append_message(
    page_dir: Path, role: str, body: str, attrs: Mapping[str, object]
) -> str:
    """log.md와 page.md의 블록 순서에 메시지 블록을 덧붙인다.

    Args:
        page_dir: 페이지 폴더.
        role: 작성자: user, router, agent 중 하나.
        body: 메시지 텍스트.
        attrs: 추가 머리 필드. 예: ``{"target": "page"}``.

    Returns:
        새 블록 id.
    """
    block_id = pages.allocate_block(page_dir)
    header = format_header(block_id, pages.now().isoformat(), role, attrs)
    log = page_dir / pages.LOG_FILE
    old = log.read_text(encoding="utf-8") if log.is_file() else ""
    prefix = old.rstrip("\n") + "\n\n" if old.strip() else ""
    text = body.strip() or "(empty)"
    pages.atomic_write(log, f"{prefix}{header}\n{text}\n")
    pages.append_block(page_dir, block_id)
    return block_id
