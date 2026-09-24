"""부작용 경로가 함께 쓰는 것: 작업할 폴더 고르기와 정책 확인.

git·실행·게시 요청은 모두 프로젝트 하나에 작용한다. 페이지를 주면 그
페이지의 워크트리(있으면)에서, 아니면 프로젝트 폴더에서 일한다. 부작용을
내기 전에 프로젝트 ``config.yaml``의 ``policy``로 확인한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from madang import config, git
from madang.api import errors
from madang.api.core import Core
from madang.policy import Policy
from madang.store import projects
from madang.store.page import work_dir


def page_in(
    core: Core, project: projects.Project, page: str | None
) -> Path | None:
    """``project``에 속한 페이지 폴더. ``page``가 없으면 None.

    Raises:
        HttpError: 페이지가 없거나(404) 다른 프로젝트의 페이지다(400).
    """
    if page is None:
        return None
    page_dir = core.page_dir(page)
    if core.project_of(page_dir).id != project.id:
        raise errors.invalid(
            f"page '{page}' does not belong to project '{project.id}'"
        )
    return page_dir


def work_folder(project: projects.Project, page_dir: Path | None) -> Path:
    """일할 폴더: 페이지 워크트리가 있으면 그것, 아니면 프로젝트 폴더.

    Raises:
        HttpError: 프로젝트 폴더가 없다(409).
    """
    if not project.root.is_dir():
        raise errors.conflict(f"project folder {project.root} does not exist")
    return work_dir(page_dir) if page_dir is not None else project.root


def require_repo(folder: Path) -> Path:
    """``folder``가 git 작업 트리인지 확인하고 반환한다.

    Raises:
        HttpError: git 저장소가 아니다(409 ``no_repo``).
    """
    if not git.is_work_tree(folder):
        raise errors.conflict(
            f"{folder} is not a git repository", errors.NO_REPO
        )
    return folder


def policy_of(project: projects.Project) -> Policy:
    """프로젝트 정책을 읽는다.

    Raises:
        ValidationFailureError: 프로젝트 ``config.yaml``이 틀렸다(400).
    """
    try:
        return Policy.load(project.root)
    except (OSError, config.ConfigError) as exc:
        raise errors.invalid(f"cannot load project config: {exc}") from exc


def allow(project: projects.Project, command: str | Sequence[str]) -> None:
    """``command``가 정책의 금지 명령이면 409 ``denied``로 막는다."""
    decision = policy_of(project).check_deny(command)
    if not decision.allowed:
        raise errors.denied(decision.reasons)
