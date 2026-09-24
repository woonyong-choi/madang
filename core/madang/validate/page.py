"""page.md checks and the page folder entry point."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from madang.store import frontmatter
from madang.store.page import PAGE_FILE, STATE_FILE, Page, space_repo
from madang.validate.issues import Issue, Lines
from madang.validate.state import DEFAULT_TOKEN_LIMIT, validate_state


def validate_page(path: Path) -> list[Issue]:
    """Check the page.md header against the page model."""
    path = Path(path)
    try:
        parts = frontmatter.split(path.read_text(encoding="utf-8"))
        header = frontmatter.load_header(parts)
    except frontmatter.FrontmatterError as exc:
        return [Issue("frontmatter", str(exc), exc.line, path)]
    except (OSError, UnicodeDecodeError) as exc:
        return [Issue("unreadable", str(exc), None, path)]
    if parts.header is None:
        return [Issue("frontmatter", "missing front matter block", 1, path)]

    lines = Lines(parts.header, parts.header_line)
    try:
        Page.model_validate(header)
    except ValidationError as exc:
        issues = []
        for err in exc.errors():
            loc = [p for p in err["loc"] if isinstance(p, (str, int))]
            name = ".".join(str(p) for p in loc) or "header"
            code = "missing-key" if err["type"] == "missing" else "invalid-value"
            line = lines.key(*loc) or parts.header_line
            issues.append(Issue(code, f"{name}: {err['msg']}", line, path))
        return issues
    return []


def resolve_target(target: Path) -> tuple[Path, Path]:
    """Return (page folder, state.md path) for a page folder or a state.md path."""
    target = Path(target)
    if target.is_dir():
        return target, target / STATE_FILE
    return target.parent, target


def validate_target(
    target: Path,
    *,
    repo: Path | None = None,
    token_limit: int = DEFAULT_TOKEN_LIMIT,
    kinds: Sequence[str] | None = None,
) -> list[Issue]:
    """Validate state.md, and page.md when present, for a page folder or state.md path.

    Without ``repo`` the space repository is taken from ``space.md``.
    """
    page_dir, state_path = resolve_target(target)
    if repo is None:
        try:
            repo = space_repo(page_dir)
        except (frontmatter.FrontmatterError, OSError):
            repo = None
    issues = validate_state(state_path, repo=repo, token_limit=token_limit, kinds=kinds)
    page_path = page_dir / PAGE_FILE
    if page_path.is_file():
        issues += validate_page(page_path)
    return issues
