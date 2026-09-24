"""뷰 템플릿 슬롯에 데이터 블록을 묶는 규칙."""

from __future__ import annotations

from madang.cli_agent.context import AgentError, PageContext
from madang.store import pages

DATA_SUFFIXES = (".json", ".csv", ".source.yaml")

Slots = list[tuple[str, bool]]


def resolve_slots(slots: Slots, data: list[str]) -> dict[str, str]:
    """``--data`` 값을 슬롯 이름에 묶는다.

    ``slot=bNN``은 그 슬롯에, 이름 없는 값은 비어 있는 슬롯에 순서대로
    묶는다.

    Args:
        slots: 템플릿의 ``(슬롯, 필수 여부)`` 목록.
        data: ``bNN`` 또는 ``slot=bNN`` 값.

    Returns:
        슬롯 순서대로 정렬한 ``슬롯 -> 블록 id``.

    Raises:
        AgentError: 없는 슬롯이거나, 같은 슬롯을 두 번 묶었거나, 값이
            남거나, 필수 슬롯이 비었다.
    """
    names = [s for s, _ in slots]
    bound: dict[str, str] = {}
    positional: list[str] = []
    for item in data:
        slot, sep, block = item.partition("=")
        if not sep:
            positional.append(item)
            continue
        if slot not in names:
            raise AgentError(
                f"템플릿에 슬롯 '{slot}'이 없다(슬롯: {', '.join(names)})"
            )
        if slot in bound:
            raise AgentError(f"슬롯 '{slot}'을 두 번 묶었다")
        bound[slot] = block
    free = [s for s in names if s not in bound]
    if len(positional) > len(free):
        raise AgentError(f"data 값이 너무 많다(슬롯: {', '.join(names)})")
    bound.update(zip(free, positional, strict=False))
    missing = [s for s, required in slots if required and s not in bound]
    if missing:
        raise AgentError(f"필수 슬롯을 묶지 않았다: {', '.join(missing)}")
    return {s: bound[s] for s in names if s in bound}


def check_data_blocks(ctx: PageContext, bound: dict[str, str]) -> None:
    """묶은 블록이 페이지의 데이터 블록인지 검사한다.

    Args:
        ctx: 뷰를 만드는 페이지.
        bound: ``슬롯 -> 블록 id``.

    Raises:
        AgentError: 블록 id가 아니거나 데이터 파일이 없다.
    """
    for slot, block in bound.items():
        if pages.parse_block_id(block) is None:
            raise AgentError(f"'{block}'는 블록 id(bNN)가 아니다")
        files = pages.block_files(ctx.page_dir, block)
        if not any(f.name.endswith(DATA_SUFFIXES) for f in files):
            raise AgentError(
                f"슬롯 '{slot}'의 데이터 블록 {block}이 blocks/에 없다"
            )
