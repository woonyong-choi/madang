"""Builds the prompt of one run and estimates its size part by part.

The prompt holds, in order: root memory, the space notes, the page state, the
shared work instructions, the target block, and the request. The runner's own
system prompt and tools are not in the prompt; their size is a per-runner
estimate (``system_est`` in runners.yaml).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from madang import contract
from madang.cli_agent.ops import BUILTIN_TEMPLATES
from madang.config import Config
from madang.store import frontmatter, pages
from madang.store.page import SPACE_FILE, STATE_FILE, space_dir, work_dir
from madang.validate import state as state_checks

ROOT_FILE = "root.md"
TEMPLATES_DIR = "templates"
TRUNCATION_MARK = "\n..."
# Measured input of a one-word run with the bundled arguments, rounded up.
DEFAULT_SYSTEM_EST = {"claude": 23000, "codex": 24000}
# State sections a promoted run (tier > 1) still reads.
PROMOTED_SECTIONS = ("막힌 점", "다음 할 일")
TOKENIZER = "cl100k_base"
FALLBACK_TOKENIZER = "utf8-bytes/3"

_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Part:
    """One section of the prompt.

    Attributes:
        name: The part name recorded in ``input.parts``.
        text: The section text as it appears in the prompt.
        tokens: The estimated tokens of ``text``.
    """

    name: str
    text: str
    tokens: int


@dataclass
class Assembled:
    """A prompt and its size estimate.

    Attributes:
        parts: The prompt sections in order.
        system_est: The estimated tokens of the runner's own system prompt.
        contract: The version of the work instructions used.
        tokenizer: The token counter used for the estimate.
        truncated: Page-relative files cut to the block limit.
    """

    parts: list[Part]
    system_est: int
    contract: str = contract.VERSION
    tokenizer: str = TOKENIZER
    truncated: list[str] = field(default_factory=list)

    @property
    def prompt(self) -> str:
        """The text handed to the runner."""
        return "\n\n".join(part.text for part in self.parts) + "\n"

    @property
    def total_est(self) -> int:
        """Estimated input tokens, runner system prompt included."""
        return self.system_est + sum(part.tokens for part in self.parts)

    def estimate(self) -> dict[str, Any]:
        """Returns the ``input`` object of a run record."""
        record: dict[str, Any] = {
            "parts": {
                "system_est": self.system_est,
                **{part.name: part.tokens for part in self.parts},
            },
            "total_est": self.total_est,
            "tokenizer": self.tokenizer,
        }
        if self.truncated:
            record["truncated"] = list(self.truncated)
        return record


def tokenizer_name() -> str:
    """Returns the token counter in use: cl100k, or the byte fallback."""
    return TOKENIZER if state_checks._encoding() else FALLBACK_TOKENIZER


def assemble(
    page_dir: Path,
    target: str | None,
    request: str,
    tier: int,
    *,
    cfg: Config,
    runner: str,
) -> Assembled:
    """Builds the prompt of one run of a page.

    Args:
        page_dir: The page folder.
        target: The id of the block the request is about, or None for the
            whole page.
        request: The message text.
        tier: The promotion tier. Above 1 only the blocked and next-step
            sections of the state are included.
        cfg: The app home configuration.
        runner: The runner name, which selects ``system_est``.

    Returns:
        The prompt and its estimate.

    Raises:
        OSError: A memory or block file cannot be read.
        ValueError: The target block has no file.
    """
    limit = cfg.madang.limits.block_input_tokens
    truncated: list[str] = []
    sections = [
        ("root", "root", _root_text(cfg.home)),
        ("space", "space", _space_text(page_dir)),
        ("state", "state", _state_text(page_dir, tier)),
        (
            "contract",
            f'instructions version="{contract.VERSION}"',
            _contract_text(page_dir, cfg),
        ),
    ]
    if target is not None:
        body = _target_text(page_dir, target, limit, truncated)
        sections.append(("target", f'target block="{target}"', body))
    sections.append(("request", "request", request.strip()))
    return Assembled(
        parts=[_part(name, tag, body) for name, tag, body in sections],
        system_est=system_estimate(cfg, runner),
        tokenizer=tokenizer_name(),
        truncated=truncated,
    )


def system_estimate(cfg: Config, runner: str) -> int:
    """Returns ``system_est`` of ``runner`` from runners.yaml.

    Args:
        cfg: The app home configuration.
        runner: The runner name.

    Returns:
        The configured value, else the built-in estimate, else 0.
    """
    spec = cfg.runners.get(runner)
    value = getattr(spec, "system_est", None) if spec else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return DEFAULT_SYSTEM_EST.get(runner, 0)


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Cuts ``text`` to at most ``limit`` tokens, keeping the start.

    Args:
        text: The text to cut.
        limit: The token limit.

    Returns:
        ``(text, cut)``. A cut text ends with ``TRUNCATION_MARK``.
    """
    if state_checks.count_tokens(text) <= limit:
        return text, False
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if state_checks.count_tokens(text[:mid] + TRUNCATION_MARK) <= limit:
            low = mid
        else:
            high = mid - 1
    return text[:low] + TRUNCATION_MARK, True


def _part(name: str, tag: str, body: str) -> Part:
    closing = tag.split(" ", 1)[0]
    text = f"<{tag}>\n{body.strip()}\n</{closing}>"
    return Part(name=name, text=text, tokens=state_checks.count_tokens(text))


def _body(path: Path) -> str:
    if not path.is_file():
        return ""
    return frontmatter.split(path.read_text(encoding="utf-8")).body


def _root_text(home: Path) -> str:
    return _body(home / ROOT_FILE)


def _space_text(page_dir: Path) -> str:
    space = space_dir(page_dir)
    return _body(space / SPACE_FILE) if space else ""


def _state_text(page_dir: Path, tier: int) -> str:
    path = page_dir / STATE_FILE
    text = path.read_text(encoding="utf-8")
    if tier <= 1:
        return f"path: {path}\n\n{text}"
    kept = [
        section
        for title, section in _sections(frontmatter.split(text).body)
        if title in PROMOTED_SECTIONS
    ]
    return f"path: {path}\n\n" + "\n".join(kept)


def _sections(body: str) -> Iterator[tuple[str, str]]:
    """Yields ``(title, text)`` for each ``## `` section of a body."""
    heads = list(_HEADING.finditer(body))
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        yield head.group(1), body[head.start() : end]


def _contract_text(page_dir: Path, cfg: Config) -> str:
    return contract.render(
        repo=str(work_dir(page_dir)),
        page=str(page_dir),
        templates=_template_names(cfg.home),
        failures=cfg.routes.limits.blocked_after_failures,
    )


def _template_names(home: Path) -> list[str]:
    installed = {
        p.parent.name for p in (home / TEMPLATES_DIR).glob("*/template.yaml")
    }
    return sorted(installed | set(BUILTIN_TEMPLATES))


def _target_text(
    page_dir: Path, block: str, limit: int, truncated: list[str]
) -> str:
    files = pages.block_files(page_dir, block)
    if not files:
        raise ValueError(f"block '{block}' has no file in blocks/")
    data = [
        path
        for bound in _bindings(files)
        for path in pages.block_files(page_dir, bound)
    ]
    chunks = []
    for path in dict.fromkeys([*files, *data]):
        rel = path.relative_to(page_dir).as_posix()
        text, cut = truncate(path.read_text(encoding="utf-8"), limit)
        if cut:
            truncated.append(rel)
        chunks.append(f'<file path="{rel}">\n{text.strip()}\n</file>')
    return "\n".join(chunks)


def _bindings(files: list[Path]) -> list[str]:
    """Returns the data block ids bound by the view files among ``files``."""
    bound: list[str] = []
    for path in files:
        if not path.name.endswith(".view.md"):
            continue
        header, _ = frontmatter.read(path)
        bindings = header.get("bindings") or {}
        if isinstance(bindings, dict):
            bound += [str(b) for b in bindings.values()]
    return bound
