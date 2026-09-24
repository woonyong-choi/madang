"""API 계약 ``openapi.yaml``: 앱과 core가 함께 따르는 진실.

설치한 패키지에서는 ``madang/openapi.yaml``(빌드 때 넣는다)을, 저장소에서
실행할 때는 ``core/openapi.yaml``을 읽는다.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

CONTRACT_FILE = "openapi.yaml"


def contract_path() -> Path:
    """계약 파일의 경로를 반환한다.

    Raises:
        FileNotFoundError: 계약 파일을 찾을 수 없다.
    """
    bundled = Path(str(resources.files("madang").joinpath(CONTRACT_FILE)))
    if bundled.is_file():
        return bundled
    source = Path(__file__).resolve().parents[2] / CONTRACT_FILE
    if source.is_file():
        return source
    raise FileNotFoundError(f"{CONTRACT_FILE} is missing from the package")


def contract_text() -> str:
    """계약 파일의 원문을 반환한다."""
    return contract_path().read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def contract_document() -> dict[str, Any]:
    """계약을 파싱한 OpenAPI 문서를 반환한다. 호출자는 고치지 않는다."""
    return yaml.safe_load(contract_text())
