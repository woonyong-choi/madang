"""페이지 대화: page.md 본문에 쌓이는 메시지 블록.

page.md 본문은 개요 뒤에 요청·실행·결과 블록이 쓰인 순서대로 쌓인다. 각
블록은 한 줄 주석 머리 ``<!-- bNN | <time> | <role> | key=value ... -->``로
시작하고 본문이 따른다. 첫 블록 머리 앞까지가 개요다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from madang.store import frontmatter, pages
from madang.store.page import PAGE_FILE

_HEAD = re.compile(
    r"^<!--\s*(?P<id>b\d+)\s*\|\s*(?P<ts>[^|]*?)\s*\|\s*(?P<role>[\w-]+)"
    r"\s*(?:\|\s*(?P<attrs>.*?))?\s*-->[ \t]*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Message:
    """page.md의 메시지 블록 하나.

    Attributes:
        id: 블록 id.
        ts: 머리 줄의 ISO 8601 시각.
        role: 작성자: user, router, agent 중 하나.
        text: 머리 줄을 뺀 본문.
        attrs: 머리 줄의 ``key=value`` 필드.
    """

    id: str
    ts: str
    role: str
    text: str
    attrs: dict[str, str] = field(default_factory=dict)


def read_messages(page_dir: Path) -> list[Message]:
    """page.md의 메시지 블록을 쓰인 순서대로 반환한다.

    Args:
        page_dir: 페이지 폴더.

    Returns:
        메시지 목록. page.md가 없으면 빈 목록.

    Raises:
        FrontmatterError: page.md 머리부를 파싱할 수 없다.
    """
    path = page_dir / PAGE_FILE
    if not path.is_file():
        return []
    _, text = frontmatter.read(path)
    heads = list(_HEAD.finditer(text))
    messages = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        messages.append(
            Message(
                id=head["id"],
                ts=head["ts"],
                role=head["role"],
                text=text[head.end() : end].strip(),
                attrs=_attrs(head["attrs"] or ""),
            )
        )
    return messages


def overview(body: str) -> str:
    """page.md 본문에서 메시지 블록 앞의 개요만 반환한다.

    Args:
        body: page.md 본문.

    Returns:
        첫 블록 머리 앞까지의 텍스트. 블록이 없으면 본문 그대로.
    """
    head = _HEAD.search(body)
    if head is None:
        return body
    text = body[: head.start()].rstrip()
    return f"{text}\n" if text else ""


def _attrs(text: str) -> dict[str, str]:
    pairs = (item.partition("=") for item in text.split())
    return {key: value for key, sep, value in pairs if sep}


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
    """page.md 본문 끝과 머리부 블록 순서에 메시지 블록을 덧붙인다.

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
    text = body.strip() or "(empty)"
    pages.append_block(page_dir, block_id, f"{header}\n{text}\n")
    return block_id
