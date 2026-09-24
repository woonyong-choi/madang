"""앱 홈 생성. 앱 홈은 전역 설정과 root.md만 두는 폴더다(git 저장소 아님)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from madang import config

MARKER = f"{config.CONFIG_DIR}/madang.yaml"
# 예전 구조(앱 홈 안에 페이지를 두던 구조)의 흔적.
LEGACY_DIR = "spaces"

# 상대 경로 -> 내장 기본 파일
_FILES: dict[str, str] = {
    **{f"{config.CONFIG_DIR}/{name}": name for name in config.CONFIG_FILES},
    "root.md": "root.md",
}
# core가 실행 중에 두는 파일. 아직 초기화 전인 폴더에 있어도 된다.
RUNTIME_FILES = (config.PORT_FILE, "core.db")


class NotAHomeError(ValueError):
    """다른 내용이 들어 있고 앱 홈이 아닌 폴더."""


class LegacyHomeError(NotAHomeError):
    """페이지를 앱 홈 안에 두던 예전 구조의 앱 홈."""


@dataclass
class InitResult:
    """``init_home``이 한 일.

    Attributes:
        home: 앱 홈 디렉터리.
        created: 만든 파일의 홈 기준 상대 경로.
    """

    home: Path
    created: list[str] = field(default_factory=list)


def init_home(home: Path) -> InitResult:
    """앱 홈에 설정 파일과 root.md를 만든다.

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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config.default_text(default), encoding="utf-8")
        result.created.append(rel)
    return result


def is_initialized(home: Path) -> bool:
    """``home``이 지금 구조로 초기화된 앱 홈인지 반환한다."""
    return (home / MARKER).is_file() and not is_legacy(home)


def is_legacy(home: Path) -> bool:
    """``home``이 페이지를 안에 두던 예전 구조인지 반환한다."""
    return (home / LEGACY_DIR).is_dir()


def check_layout(home: Path) -> None:
    """예전 구조의 앱 홈이면 옮길 방법과 함께 예외를 던진다.

    Raises:
        LegacyHomeError: ``spaces/``가 있는 예전 구조다.
    """
    if is_legacy(home):
        raise LegacyHomeError(
            f"{home} uses the old app home layout ({LEGACY_DIR}/); "
            "pages now live in <project>/.madang/. Move the folder aside, "
            "run 'madang init', then 'madang project add <path>'"
        )


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
