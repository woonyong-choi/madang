"""The page conversation: message blocks appended to ``log.md``.

Each block starts with a one-line comment header,
``<!-- bNN | <time> | <role> | key=value ... -->``, followed by its body.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from madang.store import pages


def format_header(
    block_id: str, stamp: str, role: str, attrs: Mapping[str, object]
) -> str:
    """Returns the comment line that opens a message block.

    Args:
        block_id: The block id.
        stamp: The ISO 8601 time of the message.
        role: Who wrote it: user, router, or agent.
        attrs: Extra ``key=value`` fields, in order.

    Returns:
        The header line without a trailing newline.
    """
    fields = " ".join(f"{key}={value}" for key, value in attrs.items())
    head = f"<!-- {block_id} | {stamp} | {role}"
    return f"{head} | {fields} -->" if fields else f"{head} -->"


def append_message(
    page_dir: Path, role: str, body: str, attrs: Mapping[str, object]
) -> str:
    """Appends a message block to log.md and to the page.md block order.

    Args:
        page_dir: The page folder.
        role: Who wrote it: user, router, or agent.
        body: The message text.
        attrs: Extra header fields, e.g. ``{"target": "page"}``.

    Returns:
        The new block id.
    """
    block_id = pages.allocate_block(page_dir)
    header = format_header(block_id, pages.now().isoformat(), role, attrs)
    log = page_dir / pages.LOG_FILE
    old = log.read_text(encoding="utf-8") if log.is_file() else ""
    prefix = old.rstrip("\n") + "\n\n" if old.strip() else ""
    text = body.strip() or "(empty)"
    pages.atomic_write(log, f"{prefix}{header}\n{text}\n")
    pages.append_block(page_dir, block_id)
    return block_id
