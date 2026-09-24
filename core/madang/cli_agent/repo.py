"""Code repository operations: commit, push to the current branch, file status.

Push never forces and only ever sends the checked-out branch to the branch of
the same name.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

from madang.cli_agent.context import AgentError, PageContext
from madang.store import git

# File names that must not be committed by an agent.
SENSITIVE_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "secrets.yaml",
    "secrets.yml",
    "credentials*.json",
    ".netrc",
    ".npmrc",
    ".pypirc",
)


def require_repo(ctx: PageContext) -> Path:
    """The space's code repository; refuse when there is none or it is not a git work tree."""
    repo = ctx.repo()
    if repo is None:
        raise AgentError("this page's space has no code repository (set repo in space.md)")
    if not repo.is_dir():
        raise AgentError(f"code repository {repo} does not exist")
    proc = git.run(repo, "rev-parse", "--is-inside-work-tree", check=False)
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        raise AgentError(f"{repo} is not a git repository")
    return repo


def sensitive(paths: list[str]) -> list[str]:
    return [
        p for p in paths if any(fnmatch.fnmatch(PurePosixPath(p).name, pat) for pat in SENSITIVE_NAMES)
    ]


def _changed_paths(repo: Path) -> list[str]:
    out = git.run(repo, "status", "--porcelain", "-z", "--untracked-files=all").stdout
    paths: list[str] = []
    entries = iter(out.split("\0"))
    for entry in entries:
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            next(entries, None)  # original name of a rename or copy
    return paths


def head(repo: Path) -> str:
    return git.run(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    """Stage every change in the repository and commit. Returns the short hash."""
    if not message.strip():
        raise AgentError("commit message is empty")
    changed = _changed_paths(repo)
    if not changed:
        raise AgentError("nothing to commit in the code repository")
    blocked = sensitive(changed)
    if blocked:
        raise AgentError("refusing to commit files that may hold secrets: " + ", ".join(blocked))
    try:
        git.run(repo, "add", "-A")
        if not git.has_staged_changes(repo):
            raise AgentError("nothing to commit in the code repository")
        git.commit(repo, message)
    except git.GitError as exc:
        raise AgentError(str(exc)) from exc
    return head(repo)


def commit_paths(repo: Path, paths: list[str], message: str) -> str | None:
    """Commit only ``paths``. Returns the short hash, or ``None`` when they are unchanged."""
    try:
        git.add(repo, paths)
        if git.run(repo, "diff", "--cached", "--quiet", "--", *paths, check=False).returncode == 0:
            return None
        git.commit(repo, message, paths)
    except git.GitError as exc:
        git.run(repo, "reset", "-q", "--", *paths, check=False)
        raise AgentError(str(exc)) from exc
    return head(repo)


def push_current(repo: Path) -> tuple[str, str]:
    """Push the current branch to its remote without force. Returns (remote, branch)."""
    proc = git.run(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = proc.stdout.strip()
    if proc.returncode != 0 or not branch:
        raise AgentError("HEAD is detached; check out a branch before pushing")
    remote = git.run(repo, "config", f"branch.{branch}.remote", check=False).stdout.strip()
    remotes = git.run(repo, "remote").stdout.split()
    if not remote or remote == ".":
        if "origin" not in remotes:
            raise AgentError("the code repository has no remote to push to")
        remote = "origin"
    elif remote not in remotes:
        raise AgentError(f"remote '{remote}' of branch '{branch}' does not exist")
    ref = f"refs/heads/{branch}"
    proc = git.run(repo, "push", remote, f"{ref}:{ref}", check=False)
    if proc.returncode != 0:
        raise AgentError(f"push to {remote}/{branch} failed: {proc.stderr.strip()}")
    return remote, branch
