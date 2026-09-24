"""명령이 작용할 페이지와, 검증까지 하는 보호된 쓰기."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from madang import config
from madang.runners.base import PAGE_ENV
from madang.store import runs
from madang.store.page import space_repo
from madang.store.pages import PageNotFoundError, find_page
from madang.validate import Issue, validate_target

BY_ENV = "MADANG_BY"


class AgentError(Exception):
    """거절된 요청. 메시지는 호출자에게 보여 준다."""


class PageValidationError(AgentError):
    """페이지 검증에 실패해 변경을 되돌렸다.

    Attributes:
        issues: 롤백을 일으킨 검증 이슈.
    """

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("page validation failed; changes were rolled back")
        self.issues = issues


@dataclass
class PageContext:
    """에이전트 명령이 작용하는 페이지.

    Attributes:
        home: 앱 홈 디렉터리.
        page_dir: 페이지 폴더.
        from_env: 페이지를 ``MADANG_PAGE``에서 얻었는지 여부.
        cfg: 로드된 앱 홈 설정.
    """

    home: Path
    page_dir: Path
    from_env: bool
    cfg: config.Config

    @property
    def page_id(self) -> str:
        """페이지 id. 페이지 폴더 이름이다."""
        return self.page_dir.name

    @property
    def run(self) -> int | None:
        """에이전트 실행에서 호출된 경우 진행 중인 실행."""
        return runs.current(self.page_dir) if self.from_env else None

    def by(self, explicit: str | None = None) -> str:
        """결정을 내린 사람을 반환한다.

        Args:
            explicit: ``--by``로 받은 값. 있으면.

        Returns:
            ``explicit``, 없으면 ``MADANG_BY``, 그것도 없으면 에이전트 실행
            안에서는 ``agent``, 밖에서는 ``human``.
        """
        return (
            explicit
            or os.environ.get(BY_ENV)
            or ("agent" if self.from_env else "human")
        )

    def repo(self) -> Path | None:
        """스페이스의 코드 저장소를 반환한다. 없으면 None."""
        return space_repo(self.page_dir)

    def validate(self) -> list[Issue]:
        """페이지의 검증 이슈를 반환한다."""
        return validate_target(
            self.page_dir,
            token_limit=self.cfg.madang.limits.state_tokens,
            kinds=self.cfg.routes.kinds,
        )


def resolve(page: str | None, home: Path | None) -> PageContext:
    """``--page`` 또는 ``MADANG_PAGE``로 페이지를 찾는다.

    Args:
        page: ``--page``로 받은 페이지 id. 있으면.
        home: ``--home``으로 받은 앱 홈. 있으면.

    Returns:
        페이지의 컨텍스트.

    Raises:
        AgentError: ``--page``와 ``MADANG_PAGE``가 모두 없거나, 앱 홈이나
            페이지가 없거나, 설정을 로드할 수 없다.
    """
    from_env = page is None
    page_id = page if page is not None else os.environ.get(PAGE_ENV)
    if not page_id:
        raise AgentError(
            f"{PAGE_ENV} is not set; outside an agent run pass --page <page-id>"
        )
    root = config.resolve_home(home)
    if not root.is_dir():
        raise AgentError(
            f"app home {root} does not exist; run 'madang init' first"
        )
    try:
        page_dir = find_page(root, page_id)
    except PageNotFoundError as exc:
        raise AgentError(str(exc)) from exc
    try:
        cfg = config.load_config(root)
    except Exception as exc:
        raise AgentError(f"cannot load config: {exc}") from exc
    return PageContext(home=root, page_dir=page_dir, from_env=from_env, cfg=cfg)


@dataclass
class Transaction:
    """실패한 변경을 되돌릴 수 있게 저장한 파일 내용."""

    saved: dict[Path, bytes | None] = field(default_factory=dict)
    finalizers: list[Callable[[], None]] = field(default_factory=list)

    def track(self, *paths: Path) -> None:
        """``paths``의 현재 내용을 각각 한 번씩 저장한다.

        Args:
            *paths: 롤백 때 복원할 파일. 없던 파일은 삭제한다.
        """
        for path in paths:
            if path not in self.saved:
                self.saved[path] = path.read_bytes() if path.is_file() else None

    def then(self, step: Callable[[], None]) -> None:
        """검증을 통과한 뒤 ``step``을 실행한다.

        ``step``이 실패해도 롤백한다.

        Args:
            step: 인자 없는 콜러블.
        """
        self.finalizers.append(step)

    def rollback(self) -> None:
        """추적한 모든 파일을 저장된 내용으로 복원한다."""
        for path, data in reversed(self.saved.items()):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


@contextmanager
def guarded(ctx: PageContext, *paths: Path) -> Iterator[Transaction]:
    """``paths``를 추적하고 변경을 실행한 뒤 페이지를 검증한다.

    예외나 검증 이슈가 있으면 추적한 파일을 복원한다. ``txn.then``으로
    추가한 단계는 같은 롤백 범위 안에서 마지막에 실행한다.

    Args:
        ctx: 변경 중인 페이지.
        *paths: 변경이 쓸 수 있는 파일.

    Yields:
        파일을 추적하는 트랜잭션.

    Raises:
        PageValidationError: 변경 뒤 페이지에 검증 이슈가 있다.
    """
    txn = Transaction()
    txn.track(*paths)
    try:
        yield txn
        issues = ctx.validate()
        if issues:
            raise PageValidationError(issues)
        for step in txn.finalizers:
            step()
    except BaseException:
        txn.rollback()
        raise
