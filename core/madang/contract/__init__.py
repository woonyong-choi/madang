"""The shared work instructions every run receives, kept by version.

Each version is a file ``<version>.md`` in this package. Its ``{repo}``,
``{page}``, ``{templates}``, and ``{n}`` placeholders are filled per run.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources

VERSION = "v1"


def text(version: str = VERSION) -> str:
    """Returns the raw instructions of ``version``.

    Args:
        version: The contract version, e.g. ``v1``.

    Returns:
        The file contents with placeholders left in.

    Raises:
        FileNotFoundError: No such version exists.
    """
    return (
        resources.files(__name__)
        .joinpath(f"{version}.md")
        .read_text(encoding="utf-8")
    )


def render(
    *,
    repo: str,
    page: str,
    templates: Sequence[str],
    failures: int,
    version: str = VERSION,
) -> str:
    """Returns the instructions of ``version`` for one run.

    Args:
        repo: The working folder of the run.
        page: The page folder.
        templates: The template names a view block may use.
        failures: Consecutive failures of one check before giving up.
        version: The contract version.

    Returns:
        The instructions with every placeholder filled.
    """
    values = {
        "{repo}": repo,
        "{page}": page,
        "{templates}": ", ".join(templates) or "(none)",
        "{n}": str(failures),
    }
    out = text(version)
    for key, value in values.items():
        out = out.replace(key, value)
    return out
