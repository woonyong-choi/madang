"""모든 실행이 받는 공통 작업 지시를 버전별로 보관한다.

각 버전은 이 패키지의 ``<version>.md`` 파일이다. ``{repo}``, ``{page}``,
``{templates}``, ``{n}`` 자리표시자는 실행마다 채운다.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources

VERSION = "v2"


def text(version: str = VERSION) -> str:
    """``version``의 원본 지시를 반환한다.

    Args:
        version: 계약 버전. 예: ``v1``.

    Returns:
        자리표시자가 그대로 남은 파일 내용.

    Raises:
        FileNotFoundError: 해당 버전이 없는 경우.
    """
    return (
        resources.files(__name__)
        .joinpath(f"{version}.md")
        .read_text(encoding="utf-8")
    )


def render(
    *,
    repo: str,
    page: str,
    templates: Sequence[str],
    failures: int,
    version: str = VERSION,
) -> str:
    """실행 하나에 쓸 ``version``의 지시를 반환한다.

    Args:
        repo: 실행의 작업 폴더.
        page: 페이지 폴더.
        templates: view 블록이 쓸 수 있는 템플릿 이름.
        failures: 포기하기 전 같은 검증의 연속 실패 횟수.
        version: 계약 버전.

    Returns:
        모든 자리표시자를 채운 지시.
    """
    values = {
        "{repo}": repo,
        "{page}": page,
        "{templates}": ", ".join(templates) or "(none)",
        "{n}": str(failures),
    }
    out = text(version)
    for key, value in values.items():
        out = out.replace(key, value)
    return out
