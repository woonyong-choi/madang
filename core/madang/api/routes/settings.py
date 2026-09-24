"""설정 경로: 앱 홈 ``config.yaml``과 프로젝트 ``.madang/config.yaml`` 원문.

설정(yaml)은 앱 동작만 정하며 에이전트에게 가지 않는다. 저장하기 전에
스키마로 검사하고, 틀리면 줄 번호와 키 경로를 담은 400 ``Issue``로 거부한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from madang import config
from madang.api import errors, events, models
from madang.api.routes import CoreDep, Router
from madang.store import summary
from madang.store.files import atomic_write

router = Router(tags=["setup"])

# ConfigError 한 줄: ``<파일>[:<줄>]: <키 경로>: <설명>``.
_PROBLEM = re.compile(r"^:(?P<line>\d+)?:? ?(?P<message>.*)$")


def config_issues(exc: config.ConfigError, path: Path) -> list[dict]:
    """설정 오류를 ``Issue`` 목록으로 바꾼다. 경로는 파일 이름만 둔다."""
    found = []
    prefix = str(path)
    for line in str(exc).splitlines():
        rest = line.removeprefix(prefix)
        match = _PROBLEM.match(rest) if rest != line else None
        message = match["message"] if match else line
        code = "invalid-yaml" if "invalid YAML" in message else "invalid-value"
        found.append(
            {
                "code": code,
                "message": message,
                "line": int(match["line"]) if match and match["line"] else None,
                "path": path.name,
            }
        )
    return found


def _rejected(exc: config.ConfigError, path: Path) -> Exception:
    return errors.ValidationFailureError(
        f"{path.name} failed validation", config_issues(exc, path)
    )


@router.get("/config", operation_id="getConfig")
def get_config(core: CoreDep) -> models.ConfigDocument:
    """앱 홈 config.yaml 원문. 파일이 없으면 기본값."""
    core.config()
    path = core.home / config.CONFIG_FILE
    if not path.is_file():
        return models.ConfigDocument(
            text=config.default_text(config.CONFIG_FILE)
        )
    return models.ConfigDocument(text=path.read_text(encoding="utf-8"))


@router.put("/config", operation_id="saveConfig")
def save_config(
    body: models.ConfigDocument, core: CoreDep
) -> models.ConfigDocument:
    """앱 홈 config.yaml을 검사해 통째로 바꾼다."""
    core.config()
    path = core.home / config.CONFIG_FILE
    with core.lock:
        try:
            config.parse_config(core.home, path, body.text)
        except config.ConfigError as exc:
            raise _rejected(exc, path) from exc
        atomic_write(path, body.text)
    return body


@router.get("/projects/{project}/config", operation_id="getProjectConfig")
def get_project_config(project: str, core: CoreDep) -> models.ConfigDocument:
    """프로젝트 .madang/config.yaml 원문. 파일이 없으면 빈 문자열."""
    path = config.project_config_path(core.project(project).root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return models.ConfigDocument(text=text)


@router.put("/projects/{project}/config", operation_id="saveProjectConfig")
def save_project_config(
    project: str, body: models.ConfigDocument, core: CoreDep
) -> models.ConfigDocument:
    """프로젝트 .madang/config.yaml을 검사해 통째로 바꾼다."""
    found = core.project(project)
    path = config.project_config_path(found.root)
    if not path.parent.is_dir():
        raise errors.conflict(f"{path.parent} does not exist")
    with core.lock:
        try:
            config.parse_project_config(path, body.text)
        except config.ConfigError as exc:
            raise _rejected(exc, path) from exc
        atomic_write(path, body.text)
    core.hub.emit(
        events.PROJECT_UPDATED,
        {"project": summary.project_summary(found)},
        project=found.id,
    )
    return body
