"""view 템플릿 목록과 슬롯 스키마.

앱 홈 ``templates/``에 설치한 템플릿, ``MADANG_TEMPLATES``(앱이 번들한
내장 템플릿 폴더), 내장 템플릿 이름표 순서로 찾는다. 앞에서 찾은 것이
이긴다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from madang.cli_agent.ops import BUILTIN_TEMPLATES, TEMPLATES_ENV

TEMPLATES_DIR = "templates"
TEMPLATE_FILE = "template.yaml"
SCHEMA_FILE = "schema.json"


def _sources(home: Path) -> list[tuple[Path, bool]]:
    """``(폴더, 내장 여부)`` 목록."""
    found = [(home / TEMPLATES_DIR, False)]
    extra = os.environ.get(TEMPLATES_ENV, "")
    found += [
        (Path(p).expanduser(), True) for p in extra.split(os.pathsep) if p
    ]
    return found


def _folders(home: Path) -> dict[str, tuple[Path, bool]]:
    folders: dict[str, tuple[Path, bool]] = {}
    for base, builtin in _sources(home):
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            if (folder / TEMPLATE_FILE).is_file():
                folders.setdefault(folder.name, (folder, builtin))
    return folders


def _describe(folder: Path, builtin: bool) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(
            (folder / TEMPLATE_FILE).read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    slots = []
    for name, spec in (data.get("slots") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        slot: dict[str, Any] = {
            "name": str(name),
            "required": bool(spec.get("required")),
        }
        for key in ("schema", "label"):
            if spec.get(key) is not None:
                slot[key] = str(spec[key])
        slots.append(slot)
    template: dict[str, Any] = {
        "name": str(data.get("name") or folder.name),
        "version": int(data.get("version") or 1),
        "title": str(data.get("title") or folder.name),
        "slots": slots,
        "builtin": builtin,
    }
    if isinstance(data.get("editable"), dict):
        template["editable"] = data["editable"]
    return template


def _builtin(name: str) -> dict[str, Any]:
    version, slots = BUILTIN_TEMPLATES[name]
    return {
        "name": name,
        "version": version,
        "title": name,
        "slots": [{"name": s, "required": r} for s, r in slots],
        "builtin": True,
    }


def list_templates(home: Path) -> list[dict[str, Any]]:
    """설치한 템플릿과 내장 템플릿을 이름순으로 반환한다."""
    found = {
        name: described
        for name, (folder, builtin) in _folders(home).items()
        if (described := _describe(folder, builtin)) is not None
    }
    for name in BUILTIN_TEMPLATES:
        found.setdefault(name, _builtin(name))
    return [found[name] for name in sorted(found)]


def template_schema(home: Path, name: str) -> dict[str, Any] | None:
    """템플릿의 ``schema.json``을 반환한다.

    Args:
        home: 앱 홈.
        name: 템플릿 이름.

    Returns:
        ``{name, version, schema}``. ``schema``는 JSON 텍스트. 템플릿이나
        스키마 파일이 없거나 JSON이 아니면 None.
    """
    entry = _folders(home).get(name)
    if entry is None:
        return None
    folder, builtin = entry
    described = _describe(folder, builtin)
    path = folder / SCHEMA_FILE
    if described is None or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return None
    return {"name": name, "version": described["version"], "schema": text}
