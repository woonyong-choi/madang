"""page.md 검사와 페이지 폴더 진입점."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from madang.store import frontmatter
from madang.store.page import PAGE_FILE, STATE_FILE, Page, space_repo
from madang.validate.issues import Issue, Lines
from madang.validate.state import DEFAULT_TOKEN_LIMIT, validate_state


def validate_page(path: Path) -> list[Issue]:
    """page.md 머리부를 페이지 모델에 비추어 검사한다.

    Args:
        path: page.md 파일.

    Returns:
        찾은 문제. 머리부가 올바르면 빈 목록.
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
    """검사 대상의 페이지 폴더와 state.md 경로를 반환한다.

    Args:
        target: 페이지 폴더 또는 state.md 경로.

    Returns:
        ``(페이지 폴더, state.md 경로)`` 튜플.
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
    """페이지의 state.md와, 있으면 page.md를 검사한다.

    Args:
        target: 페이지 폴더 또는 state.md 경로.
        repo: ``repo:`` 산출물의 코드 저장소. 없으면 ``space.md``의 공간
            저장소를 쓴다.
        token_limit: state.md의 최대 토큰 수.
        kinds: 허용하는 페이지 종류. 기본값은 내장 routes.yaml.

    Returns:
        찾은 문제. 페이지가 올바르면 빈 목록.
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
