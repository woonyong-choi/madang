"""되돌리기 기록: 실행 하나가 남긴 부작용과 그 역연산.

실행을 시작할 때 페이지 폴더 파일의 해시를 ``runs/N.undo.json``의
``base``에 적고, 내용은 ``runs/objects/<sha256>``에 해시 이름으로 한 번만
둔다. recorder가 그 실행의 결과를 쓸 때마다 ``base``와 지금 폴더를 비교해
``effects``를 다시 적는다. 되돌리기는 ``effects``를 거꾸로 적용한다.

부작용 종류:
    file: 페이지 폴더 파일. 실행 전 해시의 사본으로 되감는다.
    repo: 프로젝트 작업 트리 파일. 커밋·머지 기록이 되감는다.
    commit: git 커밋. 되돌림 커밋으로 되감는다.
    merge: git 머지 커밋. 첫 부모를 남기는 되돌림 커밋으로 되감는다.
    publish: 게시. 게시 모듈이 게시 기록으로 되감는다.

git 부작용은 머지 전 해시를 되돌림 기준으로 ``reset``하지 않고 되돌림
커밋(``revert``)으로 되감는다. 그 뒤에 쌓인 커밋과 이미 보낸 이력을 지우지
않고, 금지 명령(``reset --hard``)을 쓰지 않기 위해서다.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from madang import git
from madang.recorder import published
from madang.store import pages, runs
from madang.store.files import atomic_write

UNDO_SUFFIX = ".undo.json"
OBJECTS_DIR = "objects"
FILE = "file"
REPO = "repo"
REPO_PREFIX = "repo:"
COMMIT = "commit"
MERGE = "merge"
PUBLISH = "publish"
GIT_KINDS = (COMMIT, MERGE)
# 폴더 비교로 다시 찾을 수 없어 기록한 그대로 두는 부작용. 나중 것부터 되감는다.
RECORDED_KINDS = (*GIT_KINDS, PUBLISH)
# 이 모듈이 되감지 않는 부작용.
SKIPPED_KINDS = (REPO,)
# 되돌리기 대상이 아닌 페이지 폴더: 실행 기록 자체와 조립한 프롬프트.
_SKIPPED_DIRS = (runs.RUNS_DIR, pages.SCRATCH_DIR)
# 블록 번호는 되감지 않는다. 한 번 내준 id를 다시 쓰지 않기 위해서다.
_SKIPPED_FILES = (f"{pages.BLOCKS_DIR}/{pages.LAST_BLOCK_FILE}",)


class UndoError(ValueError):
    """실행을 되돌릴 수 없다."""


class UndoConflictError(UndoError):
    """실행이 바꾼 파일이 그 뒤에 다시 바뀌어 되감으면 덮어쓰게 된다.

    Attributes:
        paths: 다시 바뀐 파일(페이지 기준).
    """

    def __init__(self, paths: list[str]) -> None:
        super().__init__(f"changed after the run: {', '.join(paths)}")
        self.paths = paths


class Effect(BaseModel):
    """부작용 하나와 그것을 되감는 데 필요한 값.

    Attributes:
        kind: ``file``, ``repo``, ``commit``, ``merge``, ``publish`` 중 하나.
        path: 바뀐 것. ``file``은 페이지 기준, ``repo``는 ``repo:`` 접두,
            git 부작용은 저장소 작업 트리, 게시는 프로젝트 폴더의 절대 경로.
        before: ``file``은 실행 전 내용의 sha256(없던 파일이면 None)이며
            되감을 때 ``runs/objects/<before>`` 사본을 쓴다. git 부작용은
            커밋·머지 전 HEAD 해시.
        after: 기록 시점 내용의 sha256. 파일이 지워졌으면 None.
        commit: 되감을 커밋 해시.
        publish: 되감을 게시 번호(``.madang/published/<n>.json``).
        reverted: 되감은 되돌림 커밋 해시. 아직이면 None.
        undone: 게시를 되감았으면 참.
    """

    kind: str
    path: str | None = None
    before: str | None = None
    after: str | None = None
    commit: str | None = None
    publish: int | None = None
    reverted: str | None = None
    undone: bool = False


class UndoLog(BaseModel):
    """``runs/N.undo.json``의 내용.

    Attributes:
        n: 실행 번호.
        base: 실행 전 페이지 파일별 sha256.
        effects: 실행이 남긴 부작용.
        undone: 되돌린 시각. 아직이면 None.
    """

    n: int
    base: dict[str, str] = Field(default_factory=dict)
    effects: list[Effect] = Field(default_factory=list)
    undone: datetime | None = None


@dataclass(frozen=True)
class UndoResult:
    """되돌리기 결과.

    Attributes:
        restored: 되감은 페이지 파일.
        skipped: 이 모듈이 되감지 않는 부작용의 경로(``repo:`` 등).
        reverted: git 부작용을 되감은 되돌림 커밋 해시.
        unpublished: 되감은 게시 번호.
    """

    restored: list[str]
    skipped: list[str]
    reverted: list[str] = field(default_factory=list)
    unpublished: list[int] = field(default_factory=list)


def undo_path(page_dir: Path, n: int) -> Path:
    """``runs/N.undo.json``의 경로를 반환한다."""
    return runs.runs_dir(page_dir) / f"{n}{UNDO_SUFFIX}"


def open_log(page_dir: Path, n: int) -> UndoLog:
    """실행 전 페이지 파일을 스냅샷으로 남기고 빈 되돌리기 기록을 쓴다.

    Args:
        page_dir: 페이지 폴더.
        n: 방금 내준 실행 번호.

    Returns:
        새 기록.
    """
    base = {rel: _store(page_dir, path) for rel, path in _files(page_dir)}
    log = UndoLog(n=n, base=base)
    _write(page_dir, log)
    return log


def track(page_dir: Path, n: int) -> UndoLog | None:
    """실행 ``n``의 부작용을 지금 폴더 기준으로 다시 적는다.

    페이지 파일은 ``base``와 해시가 다른 것, 작업 트리 파일은 실행 기록의
    ``changed_files`` 중 ``repo:`` 항목이다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호.

    Returns:
        갱신한 기록. 기록이 없거나 이미 되돌린 실행이면 None.
    """
    log = read_log(page_dir, n)
    if log is None or log.undone is not None:
        return None
    now = {rel: _digest(path) for rel, path in _files(page_dir)}
    effects = [
        Effect(
            kind=FILE,
            path=rel,
            before=log.base.get(rel),
            after=now.get(rel),
        )
        for rel in sorted(log.base.keys() | now.keys())
        if log.base.get(rel) != now.get(rel)
    ]
    effects += [Effect(kind=REPO, path=p) for p in _repo_changes(page_dir, n)]
    effects += [e for e in log.effects if e.kind in RECORDED_KINDS]
    log.effects = effects
    _write(page_dir, log)
    return log


def record_git(
    page_dir: Path,
    n: int,
    kind: str,
    repo: Path,
    before: str,
    commit: str,
) -> UndoLog:
    """실행 ``n``이 만든 git 커밋이나 머지를 되돌리기 기록에 더한다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호.
        kind: ``commit`` 또는 ``merge``.
        repo: 커밋이 생긴 저장소 작업 트리.
        before: 커밋·머지 전 HEAD 해시.
        commit: 새 커밋(머지 커밋) 해시.

    Returns:
        갱신한 기록.

    Raises:
        UndoError: 종류를 모르거나, 기록이 없거나, 이미 되돌린 실행이다.
    """
    if kind not in GIT_KINDS:
        raise UndoError(f"unknown git effect: {kind}")
    log = _open_log(page_dir, n)
    if kind == MERGE:
        # 머지를 되돌리면 합친 브랜치의 커밋도 함께 되감긴다. 머지가 지운
        # 워크트리의 커밋은 따로 되감을 수 없으므로 기록에서 뺀다.
        log.effects = [e for e in log.effects if not _gone_commit(e)]
    log.effects.append(
        Effect(kind=kind, path=str(repo), before=before, commit=commit)
    )
    _write(page_dir, log)
    return log


def record_publish(page_dir: Path, n: int, root: Path, number: int) -> UndoLog:
    """실행 ``n`` 뒤에 한 게시를 되돌리기 기록에 더한다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호.
        root: 게시한 프로젝트 폴더.
        number: 게시 번호(``.madang/published/<n>.json``).

    Returns:
        갱신한 기록.

    Raises:
        UndoError: 기록이 없거나 이미 되돌린 실행이다.
    """
    log = _open_log(page_dir, n)
    log.effects.append(Effect(kind=PUBLISH, path=str(root), publish=number))
    _write(page_dir, log)
    return log


def undo(page_dir: Path, n: int) -> UndoResult:
    """실행 ``n``의 부작용을 되감는다.

    게시·git 커밋·머지는 나중 것부터(게시는 게시 모듈로, git은 되돌림
    커밋으로), 그다음 페이지 파일을 실행 전 내용으로 되감는다. 기록 뒤에
    다시 바뀐 페이지 파일이 있거나, 되감을 커밋이 이력에서 사라졌거나, 그
    게시 뒤에 다른 게시가 있으면 아무것도 바꾸지 않는다.

    Args:
        page_dir: 페이지 폴더.
        n: 실행 번호.

    Returns:
        되감은 파일, 되돌림 커밋, 건너뛴 부작용.

    Raises:
        UndoError: 기록이 없거나 이미 되돌린 실행이다.
        UndoConflictError: 실행 뒤에 다시 바뀐 파일이 있거나, 커밋이 이력에
            없거나, 더 나중 게시가 있거나, 되돌림이 충돌했다.
    """
    log = _open_log(page_dir, n)
    files = [e for e in log.effects if e.kind == FILE and e.path]
    conflicts = [e.path for e in files if _digest(page_dir / e.path) != e.after]
    recorded = [e for e in reversed(log.effects) if _pending(e)]
    conflicts += [_label(e) for e in recorded if not _reversible(e)]
    if conflicts:
        raise UndoConflictError(conflicts)
    for effect in recorded:
        _rewind(page_dir, log, effect)
    for effect in files:
        _restore(page_dir, effect)
    log.undone = pages.now()
    _write(page_dir, log)
    return UndoResult(
        restored=[e.path for e in files],
        skipped=[
            e.path or e.kind for e in log.effects if e.kind in SKIPPED_KINDS
        ],
        reverted=[e.reverted for e in log.effects if e.reverted],
        unpublished=[
            e.publish
            for e in log.effects
            if e.kind == PUBLISH and e.undone and e.publish is not None
        ],
    )


def read_log(page_dir: Path, n: int) -> UndoLog | None:
    """``runs/N.undo.json``을 읽는다. 없으면 None.

    Raises:
        ValueError: 파일이 올바른 기록이 아니다.
    """
    path = undo_path(page_dir, n)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: invalid JSON: {exc}") from exc
    return UndoLog.model_validate(data)


def _open_log(page_dir: Path, n: int) -> UndoLog:
    """아직 되돌리지 않은 실행 ``n``의 기록을 읽는다.

    Raises:
        UndoError: 기록이 없거나 이미 되돌린 실행이다.
    """
    log = read_log(page_dir, n)
    if log is None:
        raise UndoError(f"run {n} has no undo record")
    if log.undone is not None:
        raise UndoError(f"run {n} is already undone")
    return log


def _write(page_dir: Path, log: UndoLog) -> None:
    data = log.model_dump(mode="json")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write(undo_path(page_dir, log.n), text)


def _files(page_dir: Path) -> list[tuple[str, Path]]:
    """되돌리기 대상인 페이지 파일을 ``(페이지 기준 경로, 경로)``로 낸다."""
    found = []
    for current, dirs, names in os.walk(page_dir):
        base = Path(current)
        if base == page_dir:
            dirs[:] = [d for d in dirs if d not in _SKIPPED_DIRS]
        for name in names:
            path = base / name
            rel = path.relative_to(page_dir).as_posix()
            if rel not in _SKIPPED_FILES:
                found.append((rel, path))
    return sorted(found)


def _repo_changes(page_dir: Path, n: int) -> list[str]:
    if not runs.record_path(page_dir, n).is_file():
        return []
    record = runs.read_run(page_dir, n)
    return [p for p in record.changed_files if p.startswith(REPO_PREFIX)]


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object_rel(digest: str) -> str:
    return f"{runs.RUNS_DIR}/{OBJECTS_DIR}/{digest}"


def _store(page_dir: Path, path: Path) -> str:
    """``path`` 내용을 해시 이름의 사본으로 남기고 그 해시를 반환한다."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    target = page_dir / _object_rel(digest)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, data)
    return digest


def _pending(effect: Effect) -> bool:
    """기록한 부작용 중 아직 되감지 않은 것인지 여부."""
    if effect.kind in GIT_KINDS:
        return not effect.reverted
    return effect.kind == PUBLISH and not effect.undone


def _gone_commit(effect: Effect) -> bool:
    """작업 트리가 사라져 되돌림 커밋을 만들 수 없는 커밋인지 여부."""
    return (
        effect.kind == COMMIT
        and effect.path is not None
        and not Path(effect.path).is_dir()
    )


def _label(effect: Effect) -> str:
    if effect.kind == PUBLISH:
        return f"{effect.path}#publish-{effect.publish}"
    return f"{effect.path}@{(effect.commit or '')[:12]}"


def _reversible(effect: Effect) -> bool:
    """되감기 전에, 부작용이 아직 그 자리에 있는지 확인한다."""
    if effect.path is None:
        return False
    if effect.kind == PUBLISH:
        return _latest_publish(Path(effect.path)) == effect.publish
    if effect.commit is None:
        return False
    try:
        return git.is_ancestor(Path(effect.path), effect.commit)
    except git.GitError:
        return False


def _latest_publish(root: Path) -> int | None:
    try:
        record = published.latest(root)
    except published.PublishRecordError:
        return None
    return None if record is None else record.n


def _rewind(page_dir: Path, log: UndoLog, effect: Effect) -> None:
    """기록한 부작용 하나를 되감고 진행을 기록에 남긴다.

    git 되돌림이 충돌하면 그 되돌림은 취소되고, 앞서 되감은 것은 기록에
    남아 다시 시도할 때 건너뛴다.
    """
    if effect.kind == PUBLISH:
        _unpublish(effect)
    else:
        _revert(effect)
    _write(page_dir, log)


def _revert(effect: Effect) -> None:
    if effect.path is None or effect.commit is None:
        raise UndoError(f"{effect.kind} effect has no repository or commit")
    parent = 1 if effect.kind == MERGE else None
    try:
        effect.reverted = git.revert(
            Path(effect.path), effect.commit, merge_parent=parent
        )
    except git.GitError as exc:
        raise UndoConflictError([_label(effect)]) from exc


def _unpublish(effect: Effect) -> None:
    # 게시 모듈이 recorder의 게시 기록을 쓰므로 여기서 늦게 부른다.
    from madang import publish

    if effect.path is None:
        raise UndoError("publish effect has no project folder")
    try:
        publish.undo(Path(effect.path))
    except (publish.PublishError, git.GitError) as exc:
        raise UndoConflictError([_label(effect)]) from exc
    effect.undone = True


def _restore(page_dir: Path, effect: Effect) -> None:
    if effect.path is None:
        raise UndoError("file effect has no path")
    path = page_dir / effect.path
    if effect.before is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, (page_dir / _object_rel(effect.before)).read_bytes())
