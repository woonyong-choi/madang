"""프로젝트 설정 ``publish:``의 대상 해석과 게시 오류."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GH_PAGES = "gh-pages"
FOLDER_PREFIX = "folder:"
KIND_FOLDER = "folder"
KIND_BRANCH = "branch"


class PublishError(ValueError):
    """게시하거나 되감을 수 없다.

    Attributes:
        code: 짧은 kebab-case 식별자. 예: ``target-not-site``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Target:
    """게시 대상.

    Attributes:
        raw: 설정의 원문.
        kind: ``folder`` 또는 ``branch``.
        folder: 폴더 대상의 절대 경로.
        branch: 브랜치 대상의 이름.
    """

    raw: str
    kind: str
    folder: Path | None = None
    branch: str | None = None


def parse_target(raw: str | None, root: Path) -> Target:
    """``publish.target``을 해석한다.

    Args:
        raw: ``gh-pages`` 또는 ``folder:<경로>``. 경로는 프로젝트 기준
            상대 경로나 절대 경로다.
        root: 프로젝트 폴더.

    Returns:
        게시 대상.

    Raises:
        PublishError: 대상이 없거나(``target-missing``), 형식이
            틀리거나, 폴더가 프로젝트 자신이나 그 위다(``target-invalid``).
    """
    if not raw:
        raise PublishError(
            "target-missing", "publish.target is not set in config.yaml"
        )
    if raw == GH_PAGES:
        return Target(raw, KIND_BRANCH, branch=GH_PAGES)
    if not raw.startswith(FOLDER_PREFIX) or not raw[len(FOLDER_PREFIX) :]:
        raise PublishError(
            "target-invalid",
            f"publish.target must be {GH_PAGES!r} or 'folder:<path>', "
            f"got {raw!r}",
        )
    path = Path(raw[len(FOLDER_PREFIX) :]).expanduser()
    folder = (root / path).resolve()
    if root.resolve().is_relative_to(folder):
        raise PublishError(
            "target-invalid",
            f"{raw!r} is the project folder or one of its parents",
        )
    return Target(raw, KIND_FOLDER, folder=folder)
