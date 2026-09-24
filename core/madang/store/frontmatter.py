"""YAML front matter: split a Markdown file into header and body and join it back.

``split`` followed by ``join`` returns the original text byte for byte, so callers
can read the header without disturbing the body.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FENCE = "---"


class FrontmatterError(ValueError):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


@dataclass
class Parts:
    """A file cut at its front matter fences.

    ``header`` is the raw YAML between the fences (``None`` when the file has no
    front matter). ``open_nl``/``close_nl`` keep the fence line endings so that
    ``join`` is lossless.
    """

    header: str | None
    body: str
    open_nl: str = "\n"
    close_nl: str = "\n"

    @property
    def header_line(self) -> int:
        """1-based file line of the first header line."""
        return 2

    @property
    def body_line(self) -> int:
        """1-based file line where the body starts."""
        if self.header is None:
            return 1
        return self.header.count("\n") + 3


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def split(text: str) -> Parts:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != FENCE:
        return Parts(header=None, body=text)
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == FENCE:
            return Parts(
                header="".join(lines[1:i]),
                body="".join(lines[i + 1 :]),
                open_nl=_line_ending(lines[0]),
                close_nl=_line_ending(lines[i]),
            )
    raise FrontmatterError("front matter is not closed with '---'", line=1)


def join(parts: Parts) -> str:
    if parts.header is None:
        return parts.body
    return f"{FENCE}{parts.open_nl}{parts.header}{FENCE}{parts.close_nl}{parts.body}"


def load_header(parts: Parts) -> dict[str, Any]:
    """Parse the header as a YAML mapping (empty dict when there is none)."""
    if parts.header is None:
        return {}
    try:
        data = yaml.safe_load(parts.header)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = parts.header_line + mark.line if mark is not None else parts.header_line
        raise FrontmatterError(f"invalid YAML: {exc}", line=line) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FrontmatterError("front matter must be a mapping", line=parts.header_line)
    return data


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Return (header mapping, body)."""
    parts = split(text)
    return load_header(parts), parts.body


def read(path: Path) -> tuple[dict[str, Any], str]:
    return parse(path.read_text(encoding="utf-8"))


def dumps(header: dict[str, Any], body: str) -> str:
    """Build a new file from a header mapping and a body."""
    text = yaml.safe_dump(header, sort_keys=False, allow_unicode=True)
    return join(Parts(header=text, body=body))
