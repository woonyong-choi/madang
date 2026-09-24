"""Thin wrapper around the git CLI for the app home repository."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

FALLBACK_NAME = "madang"
FALLBACK_EMAIL = "madang@localhost"


class GitError(RuntimeError):
    """A git command failed or git is not installed."""


def run(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Runs git in ``repo``.

    Args:
        repo: The repository directory.
        *args: The git arguments.
        check: Whether a non-zero exit raises.

    Returns:
        The finished process with text output.

    Raises:
        GitError: git is missing, or it fails and ``check`` is true.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
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
    repo: Path, message: str, paths: Sequence[str] | None = None
) -> None:
    """Commits staged changes.

    A fallback identity is used when the repository has none.

    Args:
        repo: The repository directory.
        message: The commit message.
        paths: Limits the commit to these paths when given.

    Raises:
        GitError: The commit fails.
    """
    extra = ["--", *paths] if paths else []
    run(repo, *_identity_args(repo), "commit", "-q", "-m", message, *extra)


def log_oneline(repo: Path) -> list[str]:
    """Returns ``git log --oneline`` lines; empty when there is no commit."""
    out = run(repo, "log", "--oneline", check=False).stdout
    return [line for line in out.splitlines() if line]
