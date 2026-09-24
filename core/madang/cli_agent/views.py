"""``madang view create``: 데이터 블록에 묶인 뷰 블록을 만든다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from madang.cli_agent.artifacts import register
from madang.cli_agent.bindings import (
    Slots,
    check_data_blocks,
    resolve_slots,
)
from madang.cli_agent.context import AgentError, PageContext, guarded
from madang.cli_agent.items import is_valid_id
from madang.store import frontmatter, pages
from madang.store.page import PAGE_FILE, STATE_FILE

TEMPLATES_ENV = "MADANG_TEMPLATES"

# 앱에 포함된 템플릿: 이름 -> (버전, [(슬롯, 필수 여부)]).
BUILTIN_TEMPLATES: dict[str, tuple[int, Slots]] = {
    "table": (1, [("data", True)]),
    "decisions": (1, [("state", True)]),
    "tasks": (1, [("state", True)]),
    "resume": (1, [("base", True), ("overlay", False)]),
}


def _template_dirs(ctx: PageContext) -> list[Path]:
    dirs = [ctx.home / "templates"]
    if extra := os.environ.get(TEMPLATES_ENV):
        dirs += [Path(p).expanduser() for p in extra.split(os.pathsep) if p]
    return dirs


def _read_template(path: Path) -> tuple[int, Slots]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        slots = [
            (str(k), bool((v or {}).get("required")))
            for k, v in (data.get("slots") or {}).items()
        ]
        return int(data.get("version", 1)), slots
    except (yaml.YAMLError, AttributeError, TypeError, ValueError) as exc:
        raise AgentError(
            f"{path}: template.yaml이 올바르지 않다: {exc}"
        ) from exc


def find_template(ctx: PageContext, spec: str) -> tuple[str, int, Slots]:
    """이름으로 템플릿을 찾는다.

    앱 홈 ``templates/``, ``MADANG_TEMPLATES``, 내장 템플릿 순으로 찾는다.

    Args:
        ctx: 뷰를 만드는 페이지.
        spec: ``name`` 또는 ``name@version``.

    Returns:
        ``(name, version, slots)`` 튜플. 각 슬롯은 ``(slot, required)``.

    Raises:
        AgentError: 템플릿이 잘못됐거나, 없거나, 버전이 다르다.
    """
    name, _, want = spec.partition("@")
    if not name or not is_valid_id(name):
        raise AgentError(f"잘못된 템플릿 '{spec}'")
    found = next(
        (
            _read_template(path)
            for base in _template_dirs(ctx)
            if (path := base / name / "template.yaml").is_file()
        ),
        BUILTIN_TEMPLATES.get(name),
    )
    if found is None:
        known = ", ".join(sorted(BUILTIN_TEMPLATES))
        raise AgentError(f"템플릿 '{name}'이 없다(내장: {known})")
    version, slots = found
    if want and want != str(version):
        raise AgentError(f"템플릿 '{name}'은 버전 {version}이다({want} 아님)")
    return name, version, slots


def create_view(
    ctx: PageContext,
    template: str,
    data: list[str],
    title: str | None = None,
    run: int | None = None,
) -> str:
    """데이터 블록에 묶인 뷰 블록을 만들어 page.md에 덧붙인다.

    만든 뷰 파일은 state.md 산출물로 등록한다.

    Args:
        ctx: 변경할 페이지.
        template: 템플릿. ``find_template``가 받는 형식.
        data: 빈 슬롯에 순서대로 넣을 데이터 블록 id 또는 ``slot=bNN``.
        title: 뷰 제목.
        run: 뷰를 만든 실행 번호. 실행 밖이면 None.

    Returns:
        새 블록 id.

    Raises:
        AgentError: 템플릿이나 바인딩이 잘못됐거나 페이지 검증에 실패했다.
    """
    name, version, slots = find_template(ctx, template)
    bindings = resolve_slots(slots, data)
    check_data_blocks(ctx, bindings)
    blocks_dir = ctx.page_dir / pages.BLOCKS_DIR
    last = blocks_dir / pages.LAST_BLOCK_FILE
    tracked = (ctx.page_dir / PAGE_FILE, ctx.page_dir / STATE_FILE, last)

    with guarded(ctx, *tracked) as txn:
        block_id = pages.allocate_block(ctx.page_dir)
        path = blocks_dir / f"{block_id}-{name}.view.md"
        txn.track(path)
        header: dict[str, Any] = {
            "type": "view",
            "template": f"{name}@{version}",
        }
        if title:
            header["title"] = title
        header["bindings"] = bindings
        if run is not None:
            header["created_by"] = f"run {run}"
        path.write_text(frontmatter.dumps(header, ""), encoding="utf-8")
        pages.append_block(ctx.page_dir, block_id)
        entry = path.relative_to(ctx.page_dir).as_posix()
        pages.update_state(ctx.page_dir, lambda h: register(h, entry))
    return block_id
