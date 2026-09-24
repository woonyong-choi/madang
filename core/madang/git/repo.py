"""저장소 조작: 상태, 스테이지, 커밋, 브랜치, 머지, 되돌림, 원격, 이력."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from madang.git.command import GitError, identity_args, run

# log 출력의 필드·기록 구분자.
_FIELD = "\x1f"
_RECORD = "\x1e"


@dataclass(frozen=True)
class Commit:
    """이력의 커밋 하나.

    Attributes:
        hash: 전체 해시.
        author: 작성자 이름.
        date: 작성 시각(ISO 8601).
        subject: 메시지 첫 줄.
    """

    hash: str
    author: str
    date: str
    subject: str


@dataclass(frozen=True)
class MergeResult:
    """머지 한 번의 결과.

    Attributes:
        before: 머지 전 HEAD 해시.
        commit: 머지로 생긴 HEAD 해시. 충돌로 멈췄으면 None.
        conflicts: 충돌한 파일. 머지는 이미 취소되어 있다.
    """

    before: str
    commit: str | None = None
    conflicts: list[str] = field(default_factory=list)


# 저장소


def is_repository(folder: Path) -> bool:
    """``folder``가 git 저장소의 최상위(``.git``이 있는 폴더)인지 반환한다."""
    return (folder / ".git").exists()


def is_work_tree(folder: Path) -> bool:
    """``folder``가 git 작업 트리 안인지 반환한다."""
    proc = run(folder, "rev-parse", "--is-inside-work-tree", check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def exclude(repo: Path, pattern: str) -> bool:
    """``pattern``을 저장소의 ``info/exclude``에 더한다.

    이미 같은 줄이 있으면 그대로 둔다. 워크트리와 하위 모듈도 git이
    알려 주는 경로를 쓴다.

    Args:
        repo: 저장소 최상위 폴더.
        pattern: gitignore 형식의 한 줄.

    Returns:
        새로 더했으면 참.

    Raises:
        GitError: git이 실패했다.
        OSError: 파일을 쓸 수 없다.
    """
    found = run(repo, "rev-parse", "--git-path", "info/exclude").stdout
    path = repo / found.strip()
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if pattern in (line.strip() for line in text.splitlines()):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not text or text.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{separator}{pattern}\n")
    return True


def head(repo: Path) -> str:
    """HEAD의 짧은 해시를 반환한다."""
    return run(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def rev_parse(repo: Path, ref: str = "HEAD") -> str:
    """``ref``의 전체 해시를 반환한다.

    Raises:
        GitError: ``ref``가 없다.
    """
    return run(
        repo, "rev-parse", "--verify", f"{ref}^{{commit}}"
    ).stdout.strip()


def is_ancestor(repo: Path, commit: str, ref: str = "HEAD") -> bool:
    """``commit``이 ``ref``의 이력 안에 있는지 반환한다."""
    proc = run(repo, "merge-base", "--is-ancestor", commit, ref, check=False)
    return proc.returncode == 0


# 작업 트리와 인덱스


def status(directory: Path) -> dict[str, str]:
    """``directory`` 아래의 변경된 파일과 추적 안 되는 파일을 반환한다.

    Args:
        directory: 작업 트리 안의 폴더.

    Returns:
        ``directory`` 기준 상대 경로별 두 글자 ``git status --porcelain``
        코드(추적 안 되는 파일은 ``??``).

    Raises:
        GitError: ``directory``가 작업 트리 안이 아니거나 git이 실패했다.
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
            next(entries, None)  # 이름 변경·복사의 원래 이름
        found[path.removeprefix(prefix)] = code
    return found


def stage(repo: Path, paths: Sequence[str] | None = None) -> None:
    """변경을 스테이징한다. ``paths``가 없으면 모든 변경이다.

    Raises:
        GitError: git이 실패했다.
    """
    if paths:
        run(repo, "add", "-A", "--", *paths)
    else:
        run(repo, "add", "-A")


def has_staged_changes(repo: Path) -> bool:
    """인덱스가 HEAD와 다른지 반환한다."""
    return run(repo, "diff", "--cached", "--quiet", check=False).returncode != 0


def commit(repo: Path, message: str, paths: Sequence[str] | None = None) -> str:
    """스테이징된 변경을 커밋하고 새 HEAD의 전체 해시를 반환한다.

    저장소에 작성자 정보가 없으면 대체 정보를 쓴다.

    Args:
        repo: 저장소 디렉터리.
        message: 커밋 메시지.
        paths: 주어지면 커밋을 이 경로들로 제한한다.

    Returns:
        새 커밋의 전체 해시.

    Raises:
        GitError: 커밋이 실패했다.
    """
    extra = ["--", *paths] if paths else []
    run(repo, *identity_args(repo), "commit", "-q", "-m", message, *extra)
    return rev_parse(repo)


# 브랜치


def current_branch(repo: Path) -> str | None:
    """체크아웃된 브랜치 이름. HEAD가 분리됐으면 None."""
    proc = run(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    name = proc.stdout.strip()
    return name if proc.returncode == 0 and name else None


def branches(repo: Path) -> list[str]:
    """로컬 브랜치 이름을 정렬해 반환한다."""
    out = run(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/"
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def has_branch(repo: Path, name: str) -> bool:
    """로컬 브랜치 ``name``이 있는지 반환한다."""
    proc = run(
        repo,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{name}",
        check=False,
    )
    return proc.returncode == 0


def create_branch(repo: Path, name: str, start: str = "HEAD") -> None:
    """``start``에서 브랜치 ``name``을 만든다.

    Raises:
        GitError: 이미 있거나 ``start``가 없다.
    """
    run(repo, "branch", name, start)


def delete_branch(repo: Path, name: str) -> None:
    """머지된 브랜치 ``name``을 지운다. 머지 안 된 브랜치는 지우지 않는다.

    Raises:
        GitError: 없거나 머지되지 않았다.
    """
    run(repo, "branch", "-d", name)


# 머지와 되돌림


def merge_conflicts(repo: Path, ref: str) -> list[str]:
    """``ref``를 HEAD에 머지하면 충돌할 파일을 반환한다. 작업 트리는 그대로다.

    Raises:
        GitError: git이 머지를 계산하지 못했다.
    """
    proc = run(
        repo,
        "merge-tree",
        "--write-tree",
        "--name-only",
        "--no-messages",
        "HEAD",
        ref,
        check=False,
    )
    if proc.returncode == 0:
        return []
    if proc.returncode != 1:
        raise GitError(f"git merge-tree failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines()[1:] if line]


def merge(repo: Path, ref: str, message: str | None = None) -> MergeResult:
    """``ref``를 체크아웃된 브랜치에 머지 커밋으로 합친다.

    충돌하면 머지를 취소하고 충돌 파일을 결과에 담는다.

    Args:
        repo: 저장소 작업 트리.
        ref: 합칠 브랜치나 커밋.
        message: 머지 커밋 메시지. 없으면 git 기본 메시지.

    Returns:
        머지 전 해시와 머지 커밋 또는 충돌 파일.

    Raises:
        GitError: 충돌 밖의 이유로 머지가 실패했다.
    """
    before = rev_parse(repo)
    extra = ["-m", message] if message else []
    proc = run(
        repo,
        *identity_args(repo),
        "merge",
        "--no-ff",
        "--no-edit",
        *extra,
        ref,
        check=False,
    )
    if proc.returncode == 0:
        return MergeResult(before=before, commit=rev_parse(repo))
    conflicts = _unmerged(repo)
    run(repo, "merge", "--abort", check=False)
    if not conflicts:
        raise GitError(f"git merge {ref} failed: {proc.stderr.strip()}")
    return MergeResult(before=before, conflicts=conflicts)


def revert(
    repo: Path, commit_hash: str, *, merge_parent: int | None = None
) -> str:
    """``commit_hash``를 되돌리는 새 커밋을 만들고 그 해시를 반환한다.

    충돌하면 되돌림을 취소해 작업 트리를 원래대로 둔다.

    Args:
        repo: 저장소 작업 트리.
        commit_hash: 되돌릴 커밋.
        merge_parent: 머지 커밋이면 유지할 부모 번호(보통 1).

    Returns:
        되돌림 커밋의 전체 해시.

    Raises:
        GitError: 되돌림이 충돌했거나 실패했다.
    """
    extra = ["-m", str(merge_parent)] if merge_parent else []
    proc = run(
        repo,
        *identity_args(repo),
        "revert",
        "--no-edit",
        *extra,
        commit_hash,
        check=False,
    )
    if proc.returncode != 0:
        run(repo, "revert", "--abort", check=False)
        raise GitError(
            f"git revert {commit_hash} failed: {proc.stderr.strip()}"
        )
    return rev_parse(repo)


def _unmerged(repo: Path) -> list[str]:
    out = run(
        repo, "diff", "--name-only", "--diff-filter=U", check=False
    ).stdout
    return [line for line in out.splitlines() if line]


# 원격


def remotes(repo: Path) -> list[str]:
    """원격 이름을 반환한다."""
    return run(repo, "remote").stdout.split()


def upstream_remote(repo: Path, branch: str) -> str | None:
    """브랜치 설정에 적힌 원격 이름. 없으면 None."""
    found = run(repo, "config", f"branch.{branch}.remote", check=False).stdout
    return found.strip() or None


def push(repo: Path, remote: str, branch: str) -> None:
    """``branch``를 ``remote``의 같은 이름 브랜치로 강제 없이 보낸다.

    Raises:
        GitError: 푸시가 거부됐거나 실패했다.
    """
    ref = f"refs/heads/{branch}"
    run(repo, "push", remote, f"{ref}:{ref}")


def pull(
    repo: Path, remote: str | None = None, branch: str | None = None
) -> None:
    """빨리 감기로만 당겨 온다. 갈라졌으면 실패한다.

    Raises:
        GitError: 빨리 감기가 불가능하거나 실패했다.
    """
    target = (
        [remote, branch] if remote and branch else [remote] if remote else []
    )
    run(repo, "pull", "--ff-only", "-q", *target)


# 이력과 차이


def log(repo: Path, ref: str = "HEAD", limit: int = 50) -> list[Commit]:
    """``ref``에서 거슬러 올라가는 커밋을 최근 것부터 반환한다.

    Raises:
        GitError: ``ref``가 없다.
    """
    fmt = _FIELD.join(("%H", "%an", "%aI", "%s")) + _RECORD
    out = run(repo, "log", f"--format={fmt}", f"-n{limit}", ref, "--").stdout
    found = []
    for record in out.split(_RECORD):
        record = record.strip("\n")
        if record:
            found.append(Commit(*record.split(_FIELD, 3)))
    return found


def diff(
    repo: Path,
    base: str | None = None,
    target: str | None = None,
    *,
    staged: bool = False,
    paths: Sequence[str] = (),
) -> str:
    """차이를 통합 diff 텍스트로 반환한다.

    Args:
        repo: 저장소 작업 트리.
        base: 비교 기준. 없으면 인덱스(또는 ``staged``면 HEAD).
        target: 비교 대상. 없으면 작업 트리.
        staged: 인덱스를 HEAD(또는 ``base``)와 비교한다.
        paths: 이 경로들로 제한한다.

    Raises:
        GitError: git이 실패했다.
    """
    args = ["diff", "--no-color", "--no-ext-diff"]
    if staged:
        args.append("--cached")
    args += [ref for ref in (base, target) if ref]
    return run(repo, *args, "--", *paths).stdout
