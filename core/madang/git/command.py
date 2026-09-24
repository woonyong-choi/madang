"""git CLI를 실행하는 유일한 자리.

core 밖(앱, 에이전트 CLI)과 core의 다른 모듈은 git을 직접 실행하지 않고
``madang.git``의 함수를 쓴다. 모든 호출은 시간 제한을 두고 터미널
프롬프트를 끈다.
"""

from __future__ import annotations

import os
import subprocess
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


def identity_args(repo: Path) -> list[str]:
    """저장소에 작성자 정보가 없을 때 쓸 ``-c`` 인자를 반환한다."""
    args: list[str] = []
    if not run(repo, "config", "user.name", check=False).stdout.strip():
        args += ["-c", f"user.name={FALLBACK_NAME}"]
    if not run(repo, "config", "user.email", check=False).stdout.strip():
        args += ["-c", f"user.email={FALLBACK_EMAIL}"]
    return args
