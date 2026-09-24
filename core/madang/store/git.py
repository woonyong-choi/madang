"""Thin wrapper around the git CLI for the app home repository."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

FALLBACK_NAME = "madang"
FALLBACK_EMAIL = "madang@localhost"
TIMEOUT_SECONDS = 60.0


class GitError(RuntimeError):
    """A git command failed or git is not installed."""


def run(
    repo: Path,
    *args: str,
    check: bool = True,
    timeout: float = TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Runs git in ``repo`` without a terminal prompt.

    Args:
        repo: The repository directory.
        *args: The git arguments.
        check: Whether a non-zero exit raises.
        timeout: Seconds before git is stopped.

    Returns:
        The finished process with text output.

    Raises:
        GitError: git is missing, times out, or fails and ``check`` is true.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git {' '.join(args)} timed out after {timeout:g}s"
        ) from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def is_repo(repo: Path) -> bool:
    """Returns whether ``repo`` has a ``.git`` entry."""
    return (repo / ".git").exists()


def init(repo: Path) -> None:
    """Creates a repository with ``main`` as the initial branch."""
    run(repo, "init", "-q", "-b", "main")


def add(repo: Path, paths: Sequence[str]) -> None:
    """Stages ``paths``. Does nothing when ``paths`` is empty."""
    if paths:
        run(repo, "add", "--", *paths)


def committed_paths(repo: Path, paths: Sequence[str]) -> set[str]:
    """Returns the subset of ``paths`` present in HEAD.

    Args:
        repo: The repository directory.
        paths: Paths relative to the repository.

    Returns:
        The committed paths; empty when there is no commit yet.
    """
    if not paths:
        return set()
    proc = run(
        repo, "ls-tree", "-r", "--name-only", "HEAD", "--", *paths, check=False
    )
    if proc.returncode != 0:
        return set()
    return set(proc.stdout.splitlines())


def has_staged_changes(repo: Path) -> bool:
    """Returns whether the index differs from HEAD."""
    return run(repo, "diff", "--cached", "--quiet", check=False).returncode != 0


def _identity_args(repo: Path) -> list[str]:
    args: list[str] = []
    if not run(repo, "config", "user.name", check=False).stdout.strip():
        args += ["-c", f"user.name={FALLBACK_NAME}"]
    if not run(repo, "config", "user.email", check=False).stdout.strip():
        args += ["-c", f"user.email={FALLBACK_EMAIL}"]
    return args


def commit(
    repo: Path,
    message: str,
    paths: Sequence[str] | None = None,
    *,
    unsigned: bool = False,
) -> None:
    """Commits staged changes.

    A fallback identity is used when the repository has none.

    Args:
        repo: The repository directory.
        message: The commit message.
        paths: Limits the commit to these paths when given.
        unsigned: Skips commit signing, so a headless commit never waits for
            a signing prompt.

    Raises:
        GitError: The commit fails.
    """
    extra = ["--", *paths] if paths else []
    sign = ["-c", "commit.gpgsign=false"] if unsigned else []
    run(
        repo,
        *_identity_args(repo),
        *sign,
        "commit",
        "-q",
        "-m",
        message,
        *extra,
    )


def head(repo: Path) -> str:
    """Returns the short hash of HEAD."""
    return run(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def log_oneline(repo: Path) -> list[str]:
    """Returns ``git log --oneline`` lines; empty when there is no commit."""
    out = run(repo, "log", "--oneline", check=False).stdout
    return [line for line in out.splitlines() if line]


def status(directory: Path) -> dict[str, str]:
    """Returns the changed and untracked files under ``directory``.

    Args:
        directory: A folder inside a work tree.

    Returns:
        Each path, relative to ``directory``, mapped to its two-letter
        ``git status --porcelain`` code (``??`` for untracked files).

    Raises:
        GitError: ``directory`` is not in a work tree, or git fails.
    """
    prefix = run(directory, "rev-parse", "--show-prefix").stdout.strip()
    out = run(
        directory,
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=all",
        "--",
        ".",
    ).stdout
    found: dict[str, str] = {}
    entries = iter(out.split("\0"))
    for entry in entries:
        if not entry:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            next(entries, None)  # original name of a rename or copy
        found[path.removeprefix(prefix)] = code
    return found
