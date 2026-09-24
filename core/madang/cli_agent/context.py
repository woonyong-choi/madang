"""Which page a command acts on, and a guarded write that validates it."""

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
    """A refused request. The message is shown to the caller."""


class PageValidationError(AgentError):
    """A change was rolled back because the page failed validation.

    Attributes:
        issues: The validation issues that caused the rollback.
    """

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("page validation failed; changes were rolled back")
        self.issues = issues


@dataclass
class PageContext:
    """The page an agent command acts on.

    Attributes:
        home: The app home directory.
        page_dir: The page folder.
        from_env: Whether the page came from ``MADANG_PAGE``.
        cfg: The loaded app home configuration.
    """

    home: Path
    page_dir: Path
    from_env: bool
    cfg: config.Config

    @property
    def page_id(self) -> str:
        """The page id, which is the page folder name."""
        return self.page_dir.name

    @property
    def run(self) -> int | None:
        """Run in progress when called from an agent run."""
        return runs.current(self.page_dir) if self.from_env else None

    def by(self, explicit: str | None = None) -> str:
        """Returns who made a decision.

        Args:
            explicit: The value given with ``--by``, if any.

        Returns:
            ``explicit``, else ``MADANG_BY``, else ``agent`` inside an agent
            run and ``human`` outside one.
        """
        return (
            explicit
            or os.environ.get(BY_ENV)
            or ("agent" if self.from_env else "human")
        )

    def repo(self) -> Path | None:
        """Returns the space's code repository, or None when it has none."""
        return space_repo(self.page_dir)

    def validate(self) -> list[Issue]:
        """Returns the validation issues of the page."""
        return validate_target(
            self.page_dir,
            token_limit=self.cfg.madang.limits.state_tokens,
            kinds=self.cfg.routes.kinds,
        )


def resolve(page: str | None, home: Path | None) -> PageContext:
    """Finds the page from ``--page`` or ``MADANG_PAGE``.

    Args:
        page: The page id given with ``--page``, if any.
        home: The app home given with ``--home``, if any.

    Returns:
        The context of the page.

    Raises:
        AgentError: Neither ``--page`` nor ``MADANG_PAGE`` is set, the app
            home or the page does not exist, or the config cannot be loaded.
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
    """Saved file contents so a failed change can be undone."""

    saved: dict[Path, bytes | None] = field(default_factory=dict)
    finalizers: list[Callable[[], None]] = field(default_factory=list)

    def track(self, *paths: Path) -> None:
        """Saves the current contents of ``paths`` once each.

        Args:
            *paths: Files to restore on rollback. Missing files are deleted.
        """
        for path in paths:
            if path not in self.saved:
                self.saved[path] = path.read_bytes() if path.is_file() else None

    def then(self, step: Callable[[], None]) -> None:
        """Runs ``step`` after validation passes.

        A failure in ``step`` still rolls back.

        Args:
            step: A callable with no arguments.
        """
        self.finalizers.append(step)

    def rollback(self) -> None:
        """Restores every tracked file to its saved contents."""
        for path, data in reversed(self.saved.items()):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


@contextmanager
def guarded(ctx: PageContext, *paths: Path) -> Iterator[Transaction]:
    """Tracks ``paths``, runs the change, then validates the page.

    Any exception or validation issue restores the tracked files. Steps added
    with ``txn.then`` run last, inside the same rollback scope.

    Args:
        ctx: The page being changed.
        *paths: Files the change may write.

    Yields:
        The transaction that tracks the files.

    Raises:
        PageValidationError: The page has validation issues after the change.
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
