"""Which page a command acts on, and the guarded write that validates the page."""

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
from madang.store.pages import PageNotFound, find_page
from madang.validate import Issue, validate_target

BY_ENV = "MADANG_BY"


class AgentError(Exception):
    """A refused request. The message is shown to the caller."""


class ValidationFailed(AgentError):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("page validation failed; changes were rolled back")
        self.issues = issues


@dataclass
class PageContext:
    home: Path
    page_dir: Path
    from_env: bool
    cfg: config.Config

    @property
    def page_id(self) -> str:
        return self.page_dir.name

    @property
    def run(self) -> int | None:
        """Run in progress when called from an agent run."""
        return runs.current(self.page_dir) if self.from_env else None

    def by(self, explicit: str | None = None) -> str:
        return explicit or os.environ.get(BY_ENV) or ("agent" if self.from_env else "human")

    def repo(self) -> Path | None:
        return space_repo(self.page_dir)

    def validate(self) -> list[Issue]:
        return validate_target(
            self.page_dir,
            token_limit=self.cfg.madang.limits.state_tokens,
            kinds=self.cfg.routes.kinds,
        )


def resolve(page: str | None, home: Path | None) -> PageContext:
    """Find the page from ``--page`` or ``MADANG_PAGE``; refuse when neither is set."""
    from_env = page is None
    page_id = page if page is not None else os.environ.get(PAGE_ENV)
    if not page_id:
        raise AgentError(f"{PAGE_ENV} is not set; outside an agent run pass --page <page-id>")
    root = config.resolve_home(home)
    if not root.is_dir():
        raise AgentError(f"app home {root} does not exist; run 'madang init' first")
    try:
        page_dir = find_page(root, page_id)
    except PageNotFound as exc:
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
        for path in paths:
            if path not in self.saved:
                self.saved[path] = path.read_bytes() if path.is_file() else None

    def then(self, step: Callable[[], None]) -> None:
        """Run ``step`` after validation passes; a failure there still rolls back."""
        self.finalizers.append(step)

    def rollback(self) -> None:
        for path, data in reversed(self.saved.items()):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


@contextmanager
def guarded(ctx: PageContext, *paths: Path) -> Iterator[Transaction]:
    """Track ``paths``, run the change, then validate the page.

    Any exception or validation issue restores the tracked files. Steps added
    with ``txn.then`` run last, inside the same rollback scope.
    """
    txn = Transaction()
    txn.track(*paths)
    try:
        yield txn
        issues = ctx.validate()
        if issues:
            raise ValidationFailed(issues)
        for step in txn.finalizers:
            step()
    except BaseException:
        txn.rollback()
        raise
