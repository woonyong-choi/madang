"""문서의 view 펜스를 찾아 렌더러 context로 해석한다.

펜스 정보 문자열은 ``view <이름>[@해시] data=<경로>``이다. 렌더러
(``templates/_runtime/document.js``)의 ``listViews()``와 같은 규칙으로
``key``를 만들고, ``document_context()``가 돌려주는 ``views``를 렌더러
``renderDocument(markdown, context)``에 그대로 넘긴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from madang.viewers import schema
from madang.viewers.manifest import ViewerError
from madang.viewers.registry import (
    STATUS_BROKEN,
    STATUS_OK,
    Registry,
)

VIEW_LANG = "view"
# 데이터가 스키마와 맞지 않거나 읽을 수 없다. 렌더러는 표로 대체한다.
STATUS_INVALID = "invalid"
_FRONT_MATTER = re.compile(r"---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$)", re.S)
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_DATA_LOADERS = {
    ".json": json.loads,
    ".yaml": yaml.safe_load,
    ".yml": yaml.safe_load,
}


@dataclass(frozen=True)
class ViewRef:
    """view 펜스 참조 하나.

    Attributes:
        key: 정보 문자열에서 ``view``를 뺀 나머지. 렌더러 context의 키.
        name: 뷰어 이름.
        pin: ``@해시``. 없으면 None.
        data: ``data=`` 경로(문서 폴더 기준). 없으면 None.
    """

    key: str
    name: str
    pin: str | None = None
    data: str | None = None


@dataclass(frozen=True)
class ViewEntry:
    """렌더러 ``context.views[key]`` 항목.

    Attributes:
        status: ``ok``, ``invalid``, ``broken``, ``missing``.
        html: ``ok``일 때 뷰어 진입 HTML.
        data: 읽은 데이터.
        errors: ``invalid``일 때 안 맞는 곳.
        message: ``ok``가 아닐 때 이유.
        pin: 캐시 사본을 쓴 경우 그 해시.
    """

    status: str
    html: str | None = None
    data: Any = None
    errors: list[schema.SchemaIssue] = field(default_factory=list)
    message: str | None = None
    pin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """렌더러에 넘길 JSON 모양을 반환한다."""
        out: dict[str, Any] = {"status": self.status, "data": self.data}
        if self.html is not None:
            out["html"] = self.html
        if self.errors:
            out["errors"] = [issue.to_dict() for issue in self.errors]
        if self.message is not None:
            out["message"] = self.message
        if self.pin is not None:
            out["pin"] = self.pin
        return out


def parse_view_info(info: str) -> ViewRef | None:
    """펜스 정보 문자열을 참조로 바꾼다. view 펜스가 아니면 None."""
    words = info.split()
    if not words or words[0] != VIEW_LANG:
        return None
    target = words[1] if len(words) > 1 else ""
    name, _, pin = target.partition("@")
    data = None
    for word in words[2:]:
        if word.startswith("data="):
            data = word.removeprefix("data=")
    return ViewRef(" ".join(words[1:]), name, pin or None, data)


def find_views(markdown: str) -> list[ViewRef]:
    """문서의 view 펜스를 순서대로 찾는다. 같은 참조는 한 번만 담는다.

    Args:
        markdown: 마크다운 원문(머리부 포함 가능).

    Returns:
        펜스 참조 목록.
    """
    head = _FRONT_MATTER.match(markdown)
    body = markdown[head.end() :] if head else markdown
    found: dict[str, ViewRef] = {}
    fence: str | None = None
    for line in body.splitlines():
        match = _FENCE.match(line)
        if fence is None:
            if match is None:
                continue
            fence = match.group(1)
            ref = parse_view_info(match.group(2))
            if ref is not None:
                found.setdefault(ref.key, ref)
        elif _closes(match, fence):
            fence = None
    return list(found.values())


def resolve_view(
    ref: ViewRef,
    registry: Registry,
    *,
    document_dir: Path,
    project: Path | None = None,
) -> ViewEntry:
    """참조를 뷰어 HTML과 검사한 데이터로 해석한다.

    Args:
        ref: view 펜스 참조.
        registry: 뷰어 등록부.
        document_dir: 문서가 있는 폴더. ``data=`` 경로의 기준이다.
        project: 문서의 프로젝트 폴더. 주면 프로젝트 뷰어가 우선하고
            데이터 파일은 프로젝트 밖을 가리킬 수 없다.

    Returns:
        렌더러 context 항목. 오류는 예외 대신 상태와 이유로 담는다.
    """
    try:
        resolved = registry.resolve(ref.name, project=project, pin=ref.pin)
    except ViewerError as exc:
        return ViewEntry(STATUS_BROKEN, message=str(exc))
    try:
        data = _load_data(ref.data, document_dir, project)
    except ViewerError as exc:
        return ViewEntry(STATUS_INVALID, message=str(exc), pin=resolved.pin)
    if resolved.status != STATUS_OK or resolved.manifest is None:
        return ViewEntry(resolved.status, data=data, message=resolved.message)
    try:
        issues = schema.check(data, resolved.manifest.schema())
    except ViewerError as exc:
        return ViewEntry(STATUS_BROKEN, data=data, message=str(exc))
    if issues:
        return ViewEntry(
            STATUS_INVALID, data=data, errors=issues, pin=resolved.pin
        )
    return ViewEntry(
        STATUS_OK,
        html=resolved.manifest.entry_html(),
        data=data,
        pin=resolved.pin,
    )


def document_context(
    markdown: str,
    registry: Registry,
    *,
    document_dir: Path,
    project: Path | None = None,
) -> dict[str, Any]:
    """문서의 모든 view 펜스를 해석해 렌더러 context를 만든다.

    Args:
        markdown: 마크다운 원문.
        registry: 뷰어 등록부.
        document_dir: 문서가 있는 폴더.
        project: 문서의 프로젝트 폴더.

    Returns:
        ``{"views": {key: 항목}}``. 앱 토큰(``tokens``)은 호스트가 더한다.
    """
    return {
        "views": {
            ref.key: resolve_view(
                ref, registry, document_dir=document_dir, project=project
            ).to_dict()
            for ref in find_views(markdown)
        }
    }


def _closes(match: re.Match[str] | None, fence: str) -> bool:
    """닫는 펜스인지: 같은 문자, 같거나 긴 길이, 뒤에 공백만."""
    if match is None:
        return False
    marker, rest = match.group(1), match.group(2)
    return (
        marker[0] == fence[0]
        and len(marker) >= len(fence)
        and not (rest.strip())
    )


def _load_data(
    relative: str | None, document_dir: Path, project: Path | None
) -> Any:
    if relative is None:
        return None
    path = (document_dir / relative).resolve()
    if project is not None and not path.is_relative_to(project.resolve()):
        raise ViewerError(
            "data-outside", f"{relative!r} points outside the project"
        )
    loader = _DATA_LOADERS.get(path.suffix.lower())
    if loader is None:
        raise ViewerError(
            "data-invalid", f"{relative!r}: data must be .json or .yaml"
        )
    try:
        return loader(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        raise ViewerError("data-invalid", f"{relative!r}: {exc}") from exc
