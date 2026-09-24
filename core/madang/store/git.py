"""프로젝트 저장소용 git CLI 얇은 래퍼."""

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


def is_repository(folder: Path) -> bool:
    """``folder``가 git 저장소의 최상위(``.git``이 있는 폴더)인지 반환한다."""
    return (folder / ".git").exists()


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
    repo: Path, message: str, paths: Sequence[str] | None = None
) -> None:
    """스테이징된 변경을 커밋한다.

    저장소에 작성자 정보가 없으면 대체 정보를 쓴다.

    Args:
        repo: 저장소 디렉터리.
        message: 커밋 메시지.
        paths: 주어지면 커밋을 이 경로들로 제한한다.

    Raises:
        GitError: 커밋이 실패했다.
    """
    extra = ["--", *paths] if paths else []
    run(
        repo,
        *_identity_args(repo),
        "commit",
        "-q",
        "-m",
        message,
        *extra,
    )


def head(repo: Path) -> str:
    """HEAD의 짧은 해시를 반환한다."""
    return run(repo, "rev-parse", "--short", "HEAD").stdout.strip()


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
