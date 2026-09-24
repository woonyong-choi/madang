"""``runs:`` 선언 읽기와 쓰기."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import yaml

from madang import config
from madang.config import RunTarget


class RunsError(ValueError):
    """실행 대상 선언이나 실행 요청이 올바르지 않다."""


def targets(root: Path) -> list[RunTarget]:
    """프로젝트에 선언된 실행 대상을 선언 순서대로 반환한다.

    Args:
        root: 프로젝트 폴더.

    Raises:
        OSError: 설정 파일을 읽을 수 없는 경우.
        ConfigError: 설정이 올바르지 않은 경우.
    """
    return config.load_project_config(root).runs


def find(root: Path, name: str) -> RunTarget:
    """이름으로 선언된 실행 대상을 찾는다.

    Raises:
        RunsError: 그 이름의 선언이 없다.
    """
    for target in targets(root):
        if target.name == name:
            return target
    raise RunsError(f"run '{name}' is not declared in runs:")


def declare(
    root: Path,
    name: str,
    command: str,
    *,
    cwd: str = ".",
    opens: str | None = None,
) -> RunTarget:
    """``runs:``에 실행 대상 하나를 덧붙인다.

    다른 절과 주석은 그대로 둔다. 앱의 "선언으로 저장"과 에이전트의
    ``madang runs add``가 이 함수를 쓴다.

    Args:
        root: 프로젝트 폴더. ``.madang/``이 있어야 한다.
        name: 실행 대상 이름. 프로젝트 안에서 겹치지 않는다.
        command: 셸 명령.
        cwd: 프로젝트 폴더 기준 상대 경로.
        opens: 준비되면 브라우저로 열 URL.

    Returns:
        선언한 실행 대상.

    Raises:
        RunsError: 이름이 비었거나 겹치거나, ``cwd``가 프로젝트 밖이거나,
            ``.madang/``이 없다.
        OSError: 설정 파일을 읽거나 쓸 수 없는 경우.
        ConfigError: 기존 설정이 올바르지 않은 경우.
    """
    target = RunTarget(
        name=name.strip(), command=command.strip(), cwd=cwd, opens=opens
    )
    if not target.name or not target.command:
        raise RunsError("run name and command must not be empty")
    check_cwd(target.cwd, root)
    path = config.project_config_path(root)
    if not path.parent.is_dir():
        raise RunsError(f"{path.parent} does not exist; add the project first")
    declared = targets(root)
    if any(item.name == target.name for item in declared):
        raise RunsError(f"run '{target.name}' is already declared")
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    body = yaml.safe_dump(
        [_entry(item) for item in (*declared, target)],
        allow_unicode=True,
        sort_keys=False,
    )
    path.write_text(config.replace_section(text, "runs", body), "utf-8")
    return target


def check_cwd(cwd: str, root: Path) -> None:
    """``cwd``가 프로젝트 폴더 안을 가리키는 상대 경로인지 검사한다.

    심볼릭 링크를 따라간 실제 경로(``resolve()``)로 판단하므로 프로젝트
    안의 링크로 밖을 가리켜도 거부한다.

    Args:
        cwd: 프로젝트 폴더 기준 상대 경로.
        root: 프로젝트 폴더.

    Raises:
        RunsError: 절대 경로이거나, ``..``을 쓰거나, 실제 경로가 프로젝트
            밖이다.
    """
    path = PurePosixPath(cwd)
    outside = path.is_absolute() or ".." in path.parts
    if not outside:
        outside = not (root / cwd).resolve().is_relative_to(root.resolve())
    if outside:
        raise RunsError(f"run cwd '{cwd}' must stay inside the project")


def _entry(target: RunTarget) -> dict[str, str]:
    """``config.yaml``에 쓸 항목. 값이 기본값인 키는 뺀다."""
    entry = {"name": target.name}
    if target.cwd != ".":
        entry["cwd"] = target.cwd
    entry["command"] = target.command
    if target.opens:
        entry["opens"] = target.opens
    return entry
