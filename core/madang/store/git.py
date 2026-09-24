"""Thin wrapper around the git CLI for the app home repository."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

FALLBACK_NAME = "madang"
FALLBACK_EMAIL = "madang@localhost"


class GitError(RuntimeError):
    pass


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def is_repo(repo: Path) -> bool:
    return (repo / ".git").exists()


def init(repo: Path) -> None:
    run(repo, "init", "-q", "-b", "main")


def add(repo: Path, paths: Sequence[str]) -> None:
    if paths:
        run(repo, "add", "--", *paths)


def committed_paths(repo: Path, paths: Sequence[str]) -> set[str]:
    """Return the subset of paths present in HEAD (empty when there is no commit)."""
    if not paths:
        return set()
    proc = run(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", *paths, check=False)
    if proc.returncode != 0:
        return set()
    return set(proc.stdout.splitlines())


def has_staged_changes(repo: Path) -> bool:
    return run(repo, "diff", "--cached", "--quiet", check=False).returncode != 0


def _identity_args(repo: Path) -> list[str]:
    args: list[str] = []
    if not run(repo, "config", "user.name", check=False).stdout.strip():
        args += ["-c", f"user.name={FALLBACK_NAME}"]
    if not run(repo, "config", "user.email", check=False).stdout.strip():
        args += ["-c", f"user.email={FALLBACK_EMAIL}"]
    return args


def commit(repo: Path, message: str, paths: Sequence[str] | None = None) -> None:
    """Commit staged changes, limited to paths when given."""
    extra = ["--", *paths] if paths else []
    run(repo, *_identity_args(repo), "commit", "-q", "-m", message, *extra)


def log_oneline(repo: Path) -> list[str]:
    out = run(repo, "log", "--oneline", check=False).stdout
    return [line for line in out.splitlines() if line]
