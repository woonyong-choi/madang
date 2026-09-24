"""state.md 검사: 머리부, 결정, 산출물, 절, 크기, 완료 조건."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from madang import config
from madang.store import frontmatter
from madang.store.page import PAGE_STATUSES, latest_run
from madang.validate.issues import Issue, Lines
from madang.validate.tokens import count_tokens

DEFAULT_TOKEN_LIMIT = config.Limits().state_tokens
REQUIRED_KEYS = ("status", "kind", "tier", "attempts")
REQUIRED_SECTIONS = ("목표", "다음 할 일")
DECISION_STATES = ("proposed", "confirmed", "superseded", "deferred")
REPO_PREFIX = "repo:"

_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$")


@lru_cache(maxsize=1)
def default_kinds() -> tuple[str, ...]:
    """내장 routes.yaml에 적힌 종류를 반환한다."""
    data = yaml.safe_load(config.default_text("routes.yaml")) or {}
    return tuple(data.get("kinds") or ())


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _enum(values: Sequence[str]) -> str:
    return " | ".join(values)


def validate_state(
    path: Path,
    *,
    repo: Path | None = None,
    token_limit: int = DEFAULT_TOKEN_LIMIT,
    kinds: Sequence[str] | None = None,
) -> list[Issue]:
    """state.md 파일을 검사한다. 파일을 고치지는 않는다.

    Args:
        path: state.md 파일.
        repo: ``repo:`` 산출물의 기준인 프로젝트 폴더.
        token_limit: 파일의 최대 토큰 수.
        kinds: 허용하는 페이지 종류. 기본값은 내장 routes.yaml.

    Returns:
        찾은 문제. 파일이 올바르면 빈 목록.
    """
    path = Path(path)
    page_dir = path.parent
    kinds = tuple(kinds) if kinds is not None else default_kinds()
    issues: list[Issue] = []

    def add(
        code: str,
        message: str,
        line: int | None = None,
        where: Path | None = None,
    ) -> None:
        issues.append(
            Issue(code=code, message=message, line=line, path=where or path)
        )

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        add("missing-file", "state.md not found")
        return issues
    except (OSError, UnicodeDecodeError) as exc:
        add("unreadable", str(exc))
        return issues

    tokens = count_tokens(text)
    if tokens > token_limit:
        add(
            "token-limit",
            f"{tokens} tokens exceeds limit {token_limit}; summarize the file",
            1,
        )

    try:
        parts = frontmatter.split(text)
        header = frontmatter.load_header(parts)
    except frontmatter.FrontmatterError as exc:
        add("frontmatter", str(exc), exc.line)
        _check_sections(text, 1, add)
        return issues
    if parts.header is None:
        add("frontmatter", "missing front matter block", 1)

    lines = Lines(parts.header, parts.header_line)
    _check_header(header, lines, kinds, add)
    _check_decisions(header.get("decisions"), lines, add)
    _check_artifacts(header.get("artifacts"), lines, page_dir, repo, add)
    _check_sections(parts.body, parts.body_line, add)
    if header.get("status") == "done":
        _check_done(page_dir, lines, add)
    return issues


def _check_header(
    header: dict[str, Any], lines: Lines, kinds: Sequence[str], add: Any
) -> None:
    for key in REQUIRED_KEYS:
        if key not in header or header[key] is None:
            add(
                "missing-key",
                f"required key '{key}' is missing",
                lines.key(key) or lines.offset,
            )

    status = header.get("status")
    if status is not None and status not in PAGE_STATUSES:
        add(
            "invalid-value",
            f"status '{status}' is not one of {_enum(PAGE_STATUSES)}",
            lines.key("status"),
        )

    kind = header.get("kind")
    if kind is not None and kinds and kind not in kinds:
        add(
            "invalid-value",
            f"kind '{kind}' is not one of {_enum(kinds)}",
            lines.key("kind"),
        )

    tier = header.get("tier")
    if tier is not None and not (_is_int(tier) and tier >= 1):
        add(
            "invalid-value",
            f"tier must be an integer >= 1, got {tier!r}",
            lines.key("tier"),
        )

    attempts = header.get("attempts")
    if attempts is not None and not (_is_int(attempts) and attempts >= 0):
        add(
            "invalid-value",
            f"attempts must be an integer >= 0, got {attempts!r}",
            lines.key("attempts"),
        )


def _check_decisions(decisions: Any, lines: Lines, add: Any) -> None:
    if decisions is None:
        return
    if not isinstance(decisions, list):
        add("invalid-value", "decisions must be a list", lines.key("decisions"))
        return
    seen: dict[str, int] = {}
    for i, item in enumerate(decisions):
        line = lines.key("decisions", i)
        if not isinstance(item, dict):
            add("invalid-value", f"decisions[{i}] must be a mapping", line)
            continue
        did = item.get("id")
        if did is None:
            add("missing-key", f"decisions[{i}] has no id", line)
        elif str(did) in seen:
            add(
                "duplicate-decision",
                f"decision id '{did}' is used more than once",
                lines.key("decisions", i, "id"),
            )
        else:
            seen[str(did)] = i

        options = item.get("options")
        choice = item.get("choice")
        if options is not None and not isinstance(options, list):
            add(
                "invalid-value",
                f"decisions[{i}].options must be a list",
                lines.key("decisions", i, "options"),
            )
        elif choice is not None and choice not in (options or []):
            add(
                "choice-not-in-options",
                f"decision '{did}' choice '{choice}' is not in options",
                lines.key("decisions", i, "choice"),
            )

        state = item.get("state")
        if state is not None and state not in DECISION_STATES:
            add(
                "invalid-value",
                f"decision '{did}' state '{state}' "
                f"is not one of {_enum(DECISION_STATES)}",
                lines.key("decisions", i, "state"),
            )


def _inside(base: Path, rel: str) -> Path | None:
    """``base`` 아래에서 ``rel``을 해석한다. ``base``를 벗어나면 ``None``."""
    if not rel or Path(rel).is_absolute():
        return None
    root = base.resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        return None
    return target


def _check_artifacts(
    artifacts: Any, lines: Lines, page_dir: Path, repo: Path | None, add: Any
) -> None:
    if artifacts is None:
        return
    if not isinstance(artifacts, list):
        add("invalid-value", "artifacts must be a list", lines.key("artifacts"))
        return
    for i, item in enumerate(artifacts):
        line = lines.key("artifacts", i)
        if not isinstance(item, str) or not item.strip():
            add("invalid-value", f"artifacts[{i}] must be a path string", line)
            continue
        if item.startswith(REPO_PREFIX):
            rel = item[len(REPO_PREFIX) :]
            if repo is None:
                add(
                    "repo-unset",
                    f"artifact '{item}' needs a project folder "
                    "but the page is not in a project",
                    line,
                )
                continue
            base, where = repo, "project folder"
        else:
            rel, base, where = item, page_dir, "page folder"
        target = _inside(base, rel)
        if target is None:
            add(
                "invalid-artifact",
                f"artifact '{item}' must be a relative path inside the {where}",
                line,
            )
        elif not target.exists():
            add(
                "artifact-missing",
                f"artifact '{item}' does not exist in the {where}",
                line,
            )


def _check_sections(body: str, first_line: int, add: Any) -> None:
    found: set[str] = set()
    in_fence = False
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence and (m := _HEADING.match(raw)):
            found.add(m.group(1))
    for name in REQUIRED_SECTIONS:
        if name not in found:
            add(
                "missing-section",
                f"required section '## {name}' is missing",
                first_line,
            )


def _check_done(page_dir: Path, lines: Lines, add: Any) -> None:
    line = lines.key("status")
    try:
        run = latest_run(page_dir)
    except (OSError, ValueError) as exc:
        add(
            "done-without-verify",
            f"status is done but the last run cannot be read: {exc}",
            line,
        )
        return
    if run is None:
        add(
            "done-without-verify",
            "status is done but there is no run record",
            line,
        )
        return
    run_path, data = run
    verify = data.get("verify")
    ok = verify.get("ok") if isinstance(verify, dict) else None
    if ok is not True:
        add(
            "done-without-verify",
            f"status is done but {run_path.parent.name}/{run_path.name} "
            f"verify.ok is {ok!r}",
            line,
        )
