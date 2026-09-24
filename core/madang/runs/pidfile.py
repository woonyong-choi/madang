"""명령줄에서 띄운 실행 대상의 pid 기록.

``madang runs start``가 앞에서 도는 동안 다른 셸의 ``madang runs stop``이
그 프로세스 그룹을 찾을 수 있게 앱 홈 ``runs/``에 적어 둔다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psutil

RUNS_DIR = "runs"


def path(home: Path, project: str, name: str) -> Path:
    """``<home>/runs/<project>/<이름 해시>.json``."""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return home / RUNS_DIR / project / f"{digest}.json"


def write(home: Path, project: str, name: str, pid: int) -> Path:
    """pid와 프로세스 시작 시각을 적는다."""
    record = path(home, project, name)
    record.parent.mkdir(parents=True, exist_ok=True)
    created = psutil.Process(pid).create_time()
    payload = {"name": name, "pid": pid, "created": created}
    record.write_text(json.dumps(payload), encoding="utf-8")
    return record


def read(home: Path, project: str, name: str) -> int | None:
    """기록된 pid가 아직 같은 프로세스면 반환한다. 아니면 기록을 지운다."""
    record = path(home, project, name)
    try:
        payload = json.loads(record.read_text(encoding="utf-8"))
        pid = int(payload["pid"])
        alive = psutil.Process(pid).create_time() == payload["created"]
    except (OSError, ValueError, KeyError, TypeError, psutil.Error):
        alive = False
    if not alive:
        record.unlink(missing_ok=True)
        return None
    return pid


def remove(home: Path, project: str, name: str) -> None:
    """기록을 지운다."""
    path(home, project, name).unlink(missing_ok=True)
