"""뷰어 폴더 규격 ``viewer.json`` 읽기와 검사.

뷰어는 폴더 하나다. ``viewer.json``에 이름(``프로젝트/뷰어``), 버전,
데이터 스키마 파일, 진입 HTML 파일을 적는다. 두 파일 경로는 뷰어 폴더
기준 상대 경로이며 폴더 밖을 가리킬 수 없다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_FILE = "viewer.json"
# 이름은 "프로젝트/뷰어" 두 마디다. 예: resume/basic
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*")
_FIELDS = ("name", "version", "schema", "entry")


class ViewerError(ValueError):
    """뷰어 규격, 등록부, 해석에서 난 오류.

    Attributes:
        code: 짧은 kebab-case 식별자. 예: ``name-conflict``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Manifest:
    """검사를 통과한 ``viewer.json``.

    Attributes:
        folder: 뷰어 폴더의 절대 경로.
        name: ``프로젝트/뷰어`` 이름.
        version: 뷰어가 밝힌 버전 문자열.
        schema_path: 데이터 JSON Schema 파일.
        entry_path: 진입 HTML 파일.
    """

    folder: Path
    name: str
    version: str
    schema_path: Path
    entry_path: Path

    def schema(self) -> dict[str, Any]:
        """데이터 스키마를 읽어 반환한다.

        Raises:
            ViewerError: 스키마 파일이 JSON 객체가 아니다.
        """
        return _read_json_object(self.schema_path, "schema-invalid")

    def entry_html(self) -> str:
        """진입 HTML 텍스트를 반환한다."""
        return self.entry_path.read_text(encoding="utf-8")


def check_name(name: object) -> str:
    """뷰어 이름이 ``프로젝트/뷰어`` 꼴인지 검사한다.

    Args:
        name: 검사할 값.

    Returns:
        그대로의 이름.

    Raises:
        ViewerError: ``name-invalid``.
    """
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ViewerError(
            "name-invalid",
            f"viewer name must look like 'project/viewer' "
            f"(lowercase letters, digits, '.', '_', '-'), got {name!r}",
        )
    return name


def load_manifest(folder: Path) -> Manifest:
    """뷰어 폴더의 ``viewer.json``을 읽고 검사한다.

    Args:
        folder: 뷰어 폴더.

    Returns:
        검사한 규격.

    Raises:
        ViewerError: 파일이 없거나(``manifest-missing``), 형식이 틀리거나
            (``manifest-invalid``), 이름이 규칙에 맞지 않는다
            (``name-invalid``).
    """
    folder = folder.resolve()
    path = folder / MANIFEST_FILE
    if not path.is_file():
        raise ViewerError("manifest-missing", f"{path} not found")
    data = _read_json_object(path, "manifest-invalid")
    missing = [f for f in _FIELDS if not data.get(f)]
    if missing:
        raise ViewerError(
            "manifest-invalid", f"{path}: missing {', '.join(missing)}"
        )
    for field in ("version", "schema", "entry"):
        if not isinstance(data[field], str):
            raise ViewerError(
                "manifest-invalid", f"{path}: {field} must be a string"
            )
    return Manifest(
        folder=folder,
        name=check_name(data["name"]),
        version=data["version"],
        schema_path=_inside(folder, data["schema"], path),
        entry_path=_inside(folder, data["entry"], path),
    )


def _inside(folder: Path, relative: str, manifest: Path) -> Path:
    """뷰어 폴더 안의 존재하는 파일 경로를 반환한다."""
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder):
        raise ViewerError(
            "manifest-invalid",
            f"{manifest}: {relative!r} points outside the viewer folder",
        )
    if not target.is_file():
        raise ViewerError(
            "manifest-invalid", f"{manifest}: {relative!r} not found"
        )
    return target


def _read_json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ViewerError(code, f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ViewerError(code, f"{path}: expected a JSON object")
    return data
