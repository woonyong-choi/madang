"""게시 기록: 게시 하나를 되감는 데 필요한 값과 폴더 스냅샷.

게시할 때마다 ``<project>/.madang/published/<n>.json``에 대상, 사이트
해시, 쓴 뷰어의 고정 해시, 역연산 값을 남긴다. 폴더 대상은 게시 전후
파일 해시를 적고 게시 전 내용은 ``published/objects/<sha256>``에 해시
이름으로 한 번만 둔다. gh-pages 대상은 게시 전후 커밋을 적는다.
되감기는 게시 모듈이 이 기록을 읽어 대상에 맞게 적용한다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from madang import config
from madang.store import pages
from madang.store.files import atomic_write

PUBLISHED_DIR = "published"
OBJECTS_DIR = "objects"
_RECORD = re.compile(r"^(\d+)\.json$")


class PublishRecordError(ValueError):
    """게시 기록이 없거나 되감을 수 없다."""


class ViewerPin(BaseModel):
    """게시한 사이트에 사본으로 담은 뷰어 하나.

    Attributes:
        name: 뷰어 이름(``프로젝트/뷰어``).
        pin: 게시 시점 해시(커밋 또는 내용 해시).
    """

    name: str
    pin: str


class PublishRecord(BaseModel):
    """``published/<n>.json``의 내용.

    Attributes:
        n: 게시 번호.
        at: 게시한 시각.
        target: 설정의 대상 원문(``gh-pages`` 또는 ``folder:<경로>``).
        site: 사이트 내용 해시.
        documents: 게시한 문서(프로젝트 기준 경로).
        viewers: 사이트에 담은 뷰어와 그 해시.
        before: 폴더 대상의 게시 전 파일별 sha256.
        after: 폴더 대상의 게시 뒤 파일별 sha256.
        branch: gh-pages 대상의 브랜치.
        before_commit: 게시 전 브랜치 커밋. 브랜치가 없었으면 None.
        after_commit: 게시 커밋.
        pushed_to: 밀어 넣은 원격. 밀지 않았으면 None.
        undone: 되감은 시각. 아직이면 None.
        undo_commit: gh-pages 대상을 되감은 커밋.
    """

    n: int
    at: datetime
    target: str
    site: str
    documents: list[str] = Field(default_factory=list)
    viewers: list[ViewerPin] = Field(default_factory=list)
    before: dict[str, str] | None = None
    after: dict[str, str] | None = None
    branch: str | None = None
    before_commit: str | None = None
    after_commit: str | None = None
    pushed_to: str | None = None
    undone: datetime | None = None
    undo_commit: str | None = None


def published_dir(root: Path) -> Path:
    """``<root>/.madang/published``."""
    return root / config.PROJECT_DIR / PUBLISHED_DIR


def next_number(root: Path) -> int:
    """다음 게시 번호를 반환한다."""
    return max(_numbers(root), default=0) + 1


def save(root: Path, record: PublishRecord) -> Path:
    """게시 기록을 쓰고 경로를 반환한다."""
    path = _record_path(root, record.n)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.model_dump(mode="json")
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def read(root: Path, n: int) -> PublishRecord:
    """게시 기록 ``n``을 읽는다.

    Raises:
        PublishRecordError: 기록이 없거나 올바르지 않다.
    """
    path = _record_path(root, n)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublishRecordError(f"publish {n} has no record") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishRecordError(f"{path}: {exc}") from exc
    return PublishRecord.model_validate(data)


def latest(root: Path) -> PublishRecord | None:
    """아직 되감지 않은 가장 최근 게시 기록. 없으면 None."""
    for n in sorted(_numbers(root), reverse=True):
        record = read(root, n)
        if record.undone is None:
            return record
    return None


def mark_undone(
    root: Path, record: PublishRecord, undo_commit: str | None = None
) -> PublishRecord:
    """기록에 되감은 시각(과 되감은 커밋)을 적는다."""
    done = record.model_copy(
        update={"undone": pages.now(), "undo_commit": undo_commit}
    )
    save(root, done)
    return done


# 폴더 스냅샷


def digests(folder: Path) -> dict[str, str]:
    """폴더 안 모든 파일의 ``상대 경로 -> sha256``. 폴더가 없으면 빈 dict."""
    found: dict[str, str] = {}
    if not folder.is_dir():
        return found
    for current, _, names in os.walk(folder):
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(folder).as_posix()
            found[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(found.items()))


def snapshot(root: Path, folder: Path) -> dict[str, str]:
    """폴더 파일을 해시 이름의 사본으로 남기고 파일별 해시를 반환한다.

    Args:
        root: 프로젝트 폴더. 사본은 그 게시 기록 폴더에 둔다.
        folder: 스냅샷할 폴더.

    Returns:
        ``상대 경로 -> sha256``.
    """
    found = digests(folder)
    objects = published_dir(root) / OBJECTS_DIR
    for rel, digest in found.items():
        target = objects / digest
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, (folder / rel).read_bytes())
    return found


def restore(root: Path, folder: Path, files: dict[str, str]) -> None:
    """폴더를 ``files``(스냅샷한 해시) 상태로 되돌린다.

    ``files``에 없는 파일은 지우고, 해시가 다른 파일은 사본으로 쓴다.
    비게 된 하위 폴더는 지운다.

    Args:
        root: 프로젝트 폴더.
        folder: 되돌릴 폴더.
        files: ``snapshot()``이 돌려준 값.
    """
    now = digests(folder)
    for rel in now.keys() - files.keys():
        (folder / rel).unlink()
    objects = published_dir(root) / OBJECTS_DIR
    for rel, digest in files.items():
        if now.get(rel) == digest:
            continue
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(objects / digest, path)
    prune_empty(folder)


def prune_empty(folder: Path) -> None:
    """``folder`` 아래의 빈 하위 폴더를 지운다."""
    if not folder.is_dir():
        return
    for current, _, _ in os.walk(folder, topdown=False):
        path = Path(current)
        if path != folder and not any(path.iterdir()):
            path.rmdir()


def _record_path(root: Path, n: int) -> Path:
    return published_dir(root) / f"{n}.json"


def _numbers(root: Path) -> list[int]:
    base = published_dir(root)
    if not base.is_dir():
        return []
    return [
        int(match.group(1))
        for entry in base.iterdir()
        if (match := _RECORD.match(entry.name)) and entry.is_file()
    ]
