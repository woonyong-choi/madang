"""앱 홈 생성.

앱 홈은 나에 대한 기억(profile.md), 전역 설정(config.yaml), 뷰어
등록부(viewers.yaml), 뷰어 캐시(cache/)만 두는 폴더다(git 저장소 아님).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from madang import config

MARKER = config.CONFIG_FILE
# 나에 대한 기억(Profile). 모든 실행이 읽는다.
PROFILE_FILE = "profile.md"

# 상대 경로 -> 내장 기본 파일
_FILES: dict[str, str] = {
    PROFILE_FILE: PROFILE_FILE,
    config.CONFIG_FILE: config.CONFIG_FILE,
    config.VIEWERS_FILE: config.VIEWERS_FILE,
}
_DIRS = (config.CACHE_DIR,)
# core가 실행 중에 두는 파일. 아직 초기화 전인 폴더에 있어도 된다.
RUNTIME_FILES = (config.PORT_FILE, "core.db")
# 예전 구조의 흔적 -> 옮기는 방법
LEGACY_MARKS: dict[str, str] = {
    "spaces": (
        "pages now live in <project>/.madang/; move the folder aside, "
        "run 'madang init', then 'madang project add <path>'"
    ),
    "config": (
        "settings now live in one config.yaml; merge config/madang.yaml "
        "into it, add config/routes.yaml under 'routes:' and "
        "config/runners.yaml under 'runners:', then remove config/"
    ),
    "root.md": "the personal memory is now profile.md; rename root.md",
}


class NotAHomeError(ValueError):
    """다른 내용이 들어 있고 앱 홈이 아닌 폴더."""


class LegacyHomeError(NotAHomeError):
    """예전 구조(페이지를 안에 두던 구조, config/ 폴더, root.md)의 앱 홈."""


@dataclass
class InitResult:
    """``init_home``이 한 일.

    Attributes:
        home: 앱 홈 디렉터리.
        created: 만든 파일과 폴더(``/``로 끝남)의 홈 기준 상대 경로.
    """

    home: Path
    created: list[str] = field(default_factory=list)


def init_home(home: Path) -> InitResult:
    """앱 홈에 profile.md, config.yaml, viewers.yaml, cache/를 만든다.

    기존 파일은 절대 덮어쓰지 않는다.

    Args:
        home: 앱 홈 디렉터리.

    Returns:
        만든 것.

    Raises:
        LegacyHomeError: 예전 구조의 앱 홈이다.
        NotAHomeError: 폴더가 비어 있지 않고 ``MARKER``도 없다.
        OSError: 파일을 쓸 수 없다.
    """
    home.mkdir(parents=True, exist_ok=True)
    check_layout(home)
    _refuse_foreign(home)
    result = InitResult(home=home)
    for rel, default in _FILES.items():
        path = home / rel
        if path.exists():
            continue
        path.write_text(config.default_text(default), encoding="utf-8")
        result.created.append(rel)
    for rel in _DIRS:
        folder = home / rel
        if not folder.is_dir():
            folder.mkdir()
            result.created.append(f"{rel}/")
    return result


def is_initialized(home: Path) -> bool:
    """``home``이 지금 구조로 초기화된 앱 홈인지 반환한다."""
    return (home / MARKER).is_file() and not is_legacy(home)


def is_legacy(home: Path) -> bool:
    """``home``에 예전 구조의 흔적이 있는지 반환한다."""
    return bool(_legacy_marks(home))


def check_layout(home: Path) -> None:
    """예전 구조의 앱 홈이면 옮길 방법과 함께 예외를 던진다.

    Raises:
        LegacyHomeError: ``spaces/``, ``config/``, ``root.md`` 중 하나가
            있다.
    """
    found = _legacy_marks(home)
    if found:
        raise LegacyHomeError(
            f"{home} uses the old app home layout ({', '.join(found)}): "
            + "; ".join(LEGACY_MARKS[name] for name in found)
        )


def _legacy_marks(home: Path) -> list[str]:
    return [name for name in LEGACY_MARKS if (home / name).exists()]


def _refuse_foreign(home: Path) -> None:
    """``home``이 빈 폴더나 앱 홈이 아니면 예외를 던진다."""
    if (home / MARKER).is_file():
        return
    others = [p.name for p in home.iterdir() if p.name not in RUNTIME_FILES]
    if others:
        raise NotAHomeError(
            f"{home} is not empty and has no {MARKER}; "
            "refusing to turn it into an app home"
        )
