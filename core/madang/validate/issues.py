"""Validation issue type and YAML line lookup shared by the validators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Issue:
    """One validation problem.

    Attributes:
        code: A short kebab-case identifier, e.g. ``missing-key``.
        message: What is wrong.
        line: The 1-based file line, if known.
        path: The file, if known.
    """

    code: str
    message: str
    line: int | None = None
    path: Path | None = None

    def format(self) -> str:
        """Returns ``path:line: code message`` for terminal output."""
        where = str(self.path) if self.path is not None else "-"
        if self.line is not None:
            where = f"{where}:{self.line}"
        return f"{where}: {self.code} {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Returns the issue as a JSON-ready dict."""
        data = asdict(self)
        data["path"] = str(self.path) if self.path is not None else None
        return data


class Lines:
    """File line numbers of YAML header nodes.

    ``offset`` is the 1-based file line of the first header line.
    """

    def __init__(self, header: str | None, offset: int) -> None:
        self.offset = offset
        self.root: yaml.Node | None = None
        if header:
            try:
                self.root = yaml.compose(header, Loader=yaml.SafeLoader)
            except yaml.YAMLError:
                self.root = None

    def _line(self, node: yaml.Node) -> int:
        return self.offset + node.start_mark.line

    def key(self, *path: str | int) -> int | None:
        """Returns the file line of the key or item at ``path``.

        Args:
            *path: Mapping keys and sequence indexes from the root.

        Returns:
            The line of the deepest node found on ``path``, or None when not
            even the first part is found.
        """
        node = self.root
        line = None
        for part in path:
            found = None
            if isinstance(node, yaml.MappingNode):
                found = next(
                    (
                        (k, v)
                        for k, v in node.value
                        if isinstance(k, yaml.ScalarNode) and k.value == part
                    ),
                    None,
                )
            elif (
                isinstance(node, yaml.SequenceNode)
                and isinstance(part, int)
                and 0 <= part < len(node.value)
            ):
                found = (node.value[part], node.value[part])
            if found is None:
                return line
            line, node = self._line(found[0]), found[1]
        return line
