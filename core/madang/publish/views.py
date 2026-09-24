"""게시할 문서의 view 펜스를 해석하고 쓰인 뷰어를 게시 시점 해시로 고정한다.

펜스는 렌더러 ``listViews()``처럼 목록·인용 안에 있어도 찾는다. 줄마다
인용 표시(``>``)와 목록 표시(``-``, ``*``, ``+``, ``1.``, ``1)``)와 들여쓰기를
걷어 낸 뒤 ``madang.viewers.find_views``에 넘긴다. 들여쓴 코드 블록 안의
펜스 모양 줄도 펜스로 보므로, 렌더러보다 많이 찾을 수는 있어도 적게 찾지는
않는다. 더 찾은 항목은 렌더러가 쓰지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from madang.viewers import (
    STATUS_OK,
    Registry,
    ViewRef,
    find_views,
    resolve_view,
)
from madang.viewers.pinning import source_pin

# 줄 맨 앞의 인용 표시 하나 또는 목록 표시 하나(앞 들여쓰기 포함)
_CONTAINER = re.compile(r"[ \t]*(?:>[ \t]?|(?:[-*+]|\d{1,9}[.)])[ \t]+)")


@dataclass(frozen=True)
class PinnedCopy:
    """사이트에 사본으로 담을 뷰어 하나.

    Attributes:
        name: 뷰어 이름.
        pin: 게시 시점 해시.
        folder: 사본을 뜰 뷰어 폴더.
    """

    name: str
    pin: str
    folder: Path


@dataclass
class DocumentViews:
    """문서 하나의 렌더러 context와 쓰인 뷰어.

    Attributes:
        context: 렌더러 ``renderDocument(markdown, context)``의 context.
        copies: 사이트에 담을 뷰어 사본.
        warnings: 뷰어를 쓰지 못해 표로 대체될 펜스의 이유.
    """

    context: dict[str, Any] = field(default_factory=lambda: {"views": {}})
    copies: list[PinnedCopy] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def list_fences(markdown: str) -> list[ViewRef]:
    """문서의 view 펜스를 목록·인용 안까지 순서대로 찾는다.

    Args:
        markdown: 마크다운 원문(머리부 포함 가능).

    Returns:
        같은 참조는 한 번만 담은 펜스 참조 목록.
    """
    lines = markdown.splitlines(keepends=True)
    return find_views("".join(_unwrap(line) for line in lines))


def document_views(
    markdown: str,
    registry: Registry,
    *,
    document_dir: Path,
    project: Path,
) -> DocumentViews:
    """문서의 view 펜스를 해석하고, 쓸 수 있는 뷰어는 지금 해시로 고정한다.

    Args:
        markdown: 마크다운 원문.
        registry: 뷰어 등록부.
        document_dir: 문서가 있는 폴더(``data=`` 경로의 기준).
        project: 프로젝트 폴더.

    Returns:
        렌더러 context, 사이트에 담을 사본, 경고.
    """
    found = DocumentViews()
    for ref in list_fences(markdown):
        entry = resolve_view(
            ref, registry, document_dir=document_dir, project=project
        ).to_dict()
        if entry["status"] == STATUS_OK:
            copy = _pin(ref, registry, project)
            entry["pin"] = copy.pin
            found.copies.append(copy)
        else:
            reason = entry.get("message") or entry["status"]
            found.warnings.append(f"view {ref.key}: {reason}")
        found.context["views"][ref.key] = entry
    return found


def _pin(ref: ViewRef, registry: Registry, project: Path) -> PinnedCopy:
    """해석된 뷰어 폴더와 그 해시. 캐시 사본이면 사본의 해시를 쓴다."""
    resolved = registry.resolve(ref.name, project=project, pin=ref.pin)
    assert resolved.manifest is not None
    folder = resolved.manifest.folder
    return PinnedCopy(ref.name, resolved.pin or source_pin(folder), folder)


def _unwrap(line: str) -> str:
    while (match := _CONTAINER.match(line)) is not None:
        line = line[match.end() :]
    return line.lstrip(" \t")
