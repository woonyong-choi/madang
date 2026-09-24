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
    """Checks the page.md header against the page model.

    Args:
        path: The page.md file.

    Returns:
        The issues found; empty when the header is valid.
    """
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
            code = (
                "missing-key" if err["type"] == "missing" else "invalid-value"
            )
            line = lines.key(*loc) or parts.header_line
            issues.append(Issue(code, f"{name}: {err['msg']}", line, path))
        return issues
    return []


def resolve_target(target: Path) -> tuple[Path, Path]:
    """Returns the page folder and state.md path for a validation target.

    Args:
        target: A page folder or a state.md path.

    Returns:
        A ``(page folder, state.md path)`` tuple.
    """
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
    """Validates state.md, and page.md when present, of a page.

    Args:
        target: A page folder or a state.md path.
        repo: The code repository for ``repo:`` artifacts. Without it the
            space repository is taken from ``space.md``.
        token_limit: The maximum state.md size in tokens.
        kinds: The allowed page kinds. Defaults to the bundled routes.yaml.

    Returns:
        The issues found; empty when the page is valid.
    """
    page_dir, state_path = resolve_target(target)
    if repo is None:
        try:
            repo = space_repo(page_dir)
        except (frontmatter.FrontmatterError, OSError):
            repo = None
    issues = validate_state(
        state_path, repo=repo, token_limit=token_limit, kinds=kinds
    )
    page_path = page_dir / PAGE_FILE
    if page_path.is_file():
        issues += validate_page(page_path)
    return issues
