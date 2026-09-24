"""라우팅 표(config.yaml ``routes`` 절) 검사: 문법, 필수 키, 스키마, 참조."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from madang.config import CONFIG_FILE, ROUTES_KEY, RoutesConfig
from madang.validate.issues import Issue, Lines

# 문제의 위치 표시. 줄 번호는 절 텍스트 기준이다.
ROUTES_PATH = Path(f"{CONFIG_FILE}#{ROUTES_KEY}")
REQUIRED_KEYS = ("kinds", "default_kind", "tiers")
# 러너 이름 대신 쓸 수 있는 값: 구현한 쪽의 반대편.
OPPOSITE = "opposite"


def validate_routes(text: str, runners: Iterable[str]) -> list[Issue]:
    """``routes`` 절 텍스트를 검사한다. 파일은 쓰지 않는다.

    Args:
        text: 새 ``routes`` 절 내용(들여쓰기 없이).
        runners: ``runners`` 절에 있는 러너 이름.

    Returns:
        찾은 문제. 올바르면 빈 목록.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        return [_issue("invalid-yaml", f"invalid YAML: {exc}", line)]
    if not isinstance(data, dict):
        return [_issue("invalid-value", "routes must be a mapping", 1)]
    lines = Lines(text, 1)
    issues = [
        _issue("missing-key", f"required key '{key}' is missing", None)
        for key in REQUIRED_KEYS
        if key not in data
    ]
    if issues:
        return issues
    try:
        routes = RoutesConfig.model_validate(data)
    except ValidationError as exc:
        return [
            _issue(
                "invalid-value",
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}",
                lines.key(*err["loc"]),
            )
            for err in exc.errors()
        ]
    return _check_references(routes, set(runners), lines)


def _check_references(
    routes: RoutesConfig, runners: set[str], lines: Lines
) -> list[Issue]:
    issues = []
    if routes.default_kind not in routes.kinds:
        issues.append(
            _issue(
                "invalid-value",
                f"default_kind '{routes.default_kind}' is not in kinds",
                lines.key("default_kind"),
            )
        )
    for page_kind, kind in routes.page_kinds.items():
        if kind is not None and kind not in routes.kinds:
            issues.append(
                _issue(
                    "invalid-value",
                    f"page_kinds.{page_kind} '{kind}' is not in kinds",
                    lines.key("page_kinds", page_kind),
                )
            )
    for kind, tiers in routes.tiers.items():
        if kind not in routes.kinds:
            issues.append(
                _issue(
                    "invalid-value",
                    f"tiers has kind '{kind}' that is not in kinds",
                    lines.key("tiers", kind),
                )
            )
        for i, tier in enumerate(tiers):
            if tier.runner != OPPOSITE and tier.runner not in runners:
                issues.append(
                    _issue(
                        "invalid-value",
                        f"tiers.{kind}[{i}] runner '{tier.runner}' is not "
                        "in runners",
                        lines.key("tiers", kind, i, "runner"),
                    )
                )
    return issues


def _issue(code: str, message: str, line: Any) -> Issue:
    return Issue(code=code, message=message, line=line, path=ROUTES_PATH)
