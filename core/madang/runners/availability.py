"""러너 사용 가능 여부: 도구의 로그인 상태 명령 결과만 본다.

``claude auth status``, ``codex login status``의 종료 코드만 쓰며 출력은
응답에 담지 않는다(계정 정보가 들어 있을 수 있다). 결과는 5분간 캐시한다.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from madang.config import RunnerSpec

CACHE_SECONDS = 300.0
PROBE_TIMEOUT_SECONDS = 15.0
STATUS_ARGS = {"claude": ["auth", "status"], "codex": ["login", "status"]}

NOT_INSTALLED = "not installed"
NOT_LOGGED_IN = "not logged in"
TIMED_OUT = "status check timed out"
UNSUPPORTED = "no status check for this runner"
API_UNSUPPORTED = "api runners are not supported yet"
NOT_AVAILABLE = "not available"

Probe = Callable[[str, RunnerSpec], str | None]
"""``(러너 이름, 스펙)``을 받아 쓸 수 없는 이유를, 쓸 수 있으면 None을 준다."""


def probe_cli(name: str, spec: RunnerSpec) -> str | None:
    """로그인 상태 명령으로 구독형 CLI를 확인한다.

    Args:
        name: 러너 이름.
        spec: runners 절의 스펙.

    Returns:
        쓸 수 없는 이유. 쓸 수 있으면 None.
    """
    if spec.auth == "api":
        return API_UNSUPPORTED
    args = STATUS_ARGS.get(name)
    if args is None:
        return UNSUPPORTED
    try:
        proc = subprocess.run(
            [spec.bin, *args],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return NOT_INSTALLED
    except subprocess.TimeoutExpired:
        return TIMED_OUT
    except OSError:
        return NOT_INSTALLED
    return None if proc.returncode == 0 else NOT_LOGGED_IN


class Availability:
    """러너 확인 결과를 캐시하고, 바뀌면 알린다.

    Attributes:
        probe: 러너 하나를 확인한다.
    """

    def __init__(
        self,
        probe: Probe = probe_cli,
        on_change: Callable[[dict[str, Any]], None] = lambda _r: None,
    ) -> None:
        self.probe = probe
        self._on_change = on_change
        self._lock = threading.Lock()
        self._result: dict[str, Any] | None = None
        self._checked_at = 0.0

    def get(
        self, runners: dict[str, RunnerSpec], *, fresh: bool = False
    ) -> dict[str, Any]:
        """최근 확인 결과를 반환한다. 캐시가 지났으면 다시 확인한다.

        Args:
            runners: runners 절의 러너.
            fresh: 캐시를 무시하고 다시 확인할지 여부.

        Returns:
            ``{checked, runners: [{name, available, auth, reason}]}``.
        """
        with self._lock:
            cached = self._result
            stale = time.monotonic() - self._checked_at > CACHE_SECONDS
            names = [r["name"] for r in (cached or {}).get("runners", [])]
            reusable = cached is not None and not fresh and not stale
            if reusable and names == list(runners):
                return cached
        result = self._check(runners)
        with self._lock:
            before = self._result
            self._result, self._checked_at = result, time.monotonic()
        if before is None or before["runners"] != result["runners"]:
            self._on_change(result)
        return result

    def reason(self, name: str, runners: dict[str, RunnerSpec]) -> str | None:
        """러너 ``name``을 쓸 수 없는 이유. 쓸 수 있으면 None.

        Args:
            name: 러너 이름.
            runners: runners 절의 러너.

        Returns:
            최근 확인 결과의 이유. runners 절에 없는 러너는 None이다.
        """
        for status in self.get(runners)["runners"]:
            if status["name"] == name and not status["available"]:
                return status["reason"] or NOT_AVAILABLE
        return None

    def _check(self, runners: dict[str, RunnerSpec]) -> dict[str, Any]:
        statuses = []
        for name, spec in runners.items():
            reason = self.probe(name, spec)
            statuses.append(
                {
                    "name": name,
                    "available": reason is None,
                    "auth": spec.auth
                    if spec.auth in ("subscription", "api")
                    else None,
                    "reason": reason,
                }
            )
        checked = datetime.now().astimezone().replace(microsecond=0)
        return {"checked": checked.isoformat(), "runners": statuses}
