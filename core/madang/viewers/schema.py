"""뷰어 데이터의 JSON Schema 검사.

뷰어 스키마가 쓰는 부분만 검사한다: ``type``, ``enum``, ``const``,
``required``, ``properties``, ``additionalProperties``, ``items``, 문서
안 ``$ref``(``#/...``). 그 밖의 키워드는 검사하지 않는다. 문제마다
데이터의 어디가 안 맞는지 경로(``work[1].company``)를 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from madang.viewers.manifest import ViewerError

type Segment = str | int


@dataclass(frozen=True)
class SchemaIssue:
    """데이터가 스키마와 맞지 않는 곳 하나.

    Attributes:
        path: 데이터 경로. 최상위는 빈 문자열이다.
        message: 무엇이 안 맞는지.
    """

    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """JSON으로 바꿀 수 있는 dict를 반환한다."""
        return {"path": self.path, "message": self.message}


def check(data: Any, schema: dict[str, Any]) -> list[SchemaIssue]:
    """데이터를 스키마로 검사한다.

    Args:
        data: JSON 값.
        schema: JSON Schema 객체.

    Returns:
        안 맞는 곳 목록. 비어 있으면 통과다.

    Raises:
        ViewerError: 스키마의 ``$ref``를 풀 수 없다(``schema-invalid``).
    """
    issues: list[SchemaIssue] = []
    _check(data, schema, schema, [], issues)
    return issues


def format_path(segments: list[Segment]) -> str:
    """경로 마디를 ``work[1].company`` 꼴로 이어 붙인다."""
    out = ""
    for seg in segments:
        if isinstance(seg, int):
            out += f"[{seg}]"
        else:
            out += f".{seg}" if out else seg
    return out


def _check(
    value: Any,
    node: Any,
    root: dict[str, Any],
    path: list[Segment],
    issues: list[SchemaIssue],
) -> None:
    if node is False:
        issues.append(SchemaIssue(format_path(path), "value is not allowed"))
        return
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        _check(value, _resolve_ref(root, node["$ref"]), root, path, issues)
    if not _check_value(value, node, path, issues):
        return
    if isinstance(value, dict):
        _check_object(value, node, root, path, issues)
    elif isinstance(value, list) and "items" in node:
        for i, item in enumerate(value):
            _check(item, node["items"], root, [*path, i], issues)


def _check_value(
    value: Any,
    node: dict[str, Any],
    path: list[Segment],
    issues: list[SchemaIssue],
) -> bool:
    """type·enum·const를 검사하고, 더 들어가도 되는지 반환한다."""
    where = format_path(path)
    if "type" in node:
        allowed = node["type"]
        names = allowed if isinstance(allowed, list) else [allowed]
        if not any(_is_type(value, name) for name in names):
            issues.append(
                SchemaIssue(
                    where,
                    f"expected {' or '.join(names)}, got {_type_name(value)}",
                )
            )
            return False
    if "enum" in node and value not in node["enum"]:
        issues.append(SchemaIssue(where, f"must be one of {node['enum']}"))
    if "const" in node and value != node["const"]:
        issues.append(SchemaIssue(where, f"must be {node['const']!r}"))
    return True


def _check_object(
    value: dict[str, Any],
    node: dict[str, Any],
    root: dict[str, Any],
    path: list[Segment],
    issues: list[SchemaIssue],
) -> None:
    for key in node.get("required", []):
        if key not in value:
            issues.append(SchemaIssue(format_path([*path, key]), "is required"))
    properties = node.get("properties", {})
    extra = node.get("additionalProperties", True)
    for key, item in value.items():
        if key in properties:
            _check(item, properties[key], root, [*path, key], issues)
        elif extra is False:
            issues.append(
                SchemaIssue(format_path([*path, key]), "is not allowed")
            )
        else:
            _check(item, extra, root, [*path, key], issues)


def _resolve_ref(root: dict[str, Any], ref: object) -> Any:
    if not isinstance(ref, str) or not ref.startswith("#"):
        raise ViewerError("schema-invalid", f"unsupported $ref {ref!r}")
    node: Any = root
    for raw in ref[1:].split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or key not in node:
            raise ViewerError("schema-invalid", f"cannot resolve $ref {ref!r}")
        node = node[key]
    return node


def _is_type(value: Any, name: str) -> bool:
    match name:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "boolean":
            return isinstance(value, bool)
        case "null":
            return value is None
        case "number":
            return isinstance(value, int | float) and not isinstance(
                value, bool
            )
        case "integer":
            if isinstance(value, bool):
                return False
            return isinstance(value, int) or (
                isinstance(value, float) and value.is_integer()
            )
    raise ViewerError("schema-invalid", f"unknown type {name!r}")


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"
