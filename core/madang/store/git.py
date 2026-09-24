"""앱 홈 저장소용 git CLI 얇은 래퍼."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

FALLBACK_NAME = "madang"
FALLBACK_EMAIL = "madang@localhost"
TIMEOUT_SECONDS = 60.0


class GitError(RuntimeError):
    """git 명령이 실패했거나 git이 설치되어 있지 않다."""


def run(
    repo: Path,
    *args: str,
    check: bool = True,
    timeout: float = TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """터미널 프롬프트 없이 ``repo``에서 git을 실행한다.

    Args:
        repo: 저장소 디렉터리.
        *args: git 인자.
        check: 0이 아닌 종료 코드에서 예외를 던질지 여부.
        timeout: git을 중단하기까지의 초.

    Returns:
        텍스트 출력을 가진 종료된 프로세스.

    Raises:
        GitError: git이 없거나, 시간 초과되거나, ``check``가 참일 때 실패했다.
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
    """``repo``에 ``.git`` 항목이 있는지 반환한다."""
    return (repo / ".git").exists()


def init(repo: Path) -> None:
    """``main``을 초기 브랜치로 하는 저장소를 만든다."""
    run(repo, "init", "-q", "-b", "main")


def add(repo: Path, paths: Sequence[str]) -> None:
    """``paths``를 스테이징한다. 비어 있으면 아무것도 하지 않는다."""
    if paths:
        run(repo, "add", "--", *paths)


def committed_paths(repo: Path, paths: Sequence[str]) -> set[str]:
    """``paths`` 중 HEAD에 있는 부분집합을 반환한다.

    Args:
        repo: 저장소 디렉터리.
        paths: 저장소 기준 상대 경로.

    Returns:
        커밋된 경로. 아직 커밋이 없으면 빈 집합.
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
    """인덱스가 HEAD와 다른지 반환한다."""
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
    """스테이징된 변경을 커밋한다.

    저장소에 작성자 정보가 없으면 대체 정보를 쓴다.

    Args:
        repo: 저장소 디렉터리.
        message: 커밋 메시지.
        paths: 주어지면 커밋을 이 경로들로 제한한다.
        unsigned: 커밋 서명을 건너뛰어, 헤드리스 커밋이 서명 프롬프트를
            기다리지 않게 한다.

    Raises:
        GitError: 커밋이 실패했다.
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
    """HEAD의 짧은 해시를 반환한다."""
    return run(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def log_oneline(repo: Path) -> list[str]:
    """``git log --oneline`` 줄을 반환한다. 커밋이 없으면 빈 목록."""
    out = run(repo, "log", "--oneline", check=False).stdout
    return [line for line in out.splitlines() if line]


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
