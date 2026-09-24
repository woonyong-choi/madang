"""뷰어 등록부 ``~/.madang/viewers.yaml`` 읽기·쓰기와 이름 해석.

등록은 참조다. 항목은 뷰어 폴더(``source``)를 가리킬 뿐 복사하지 않는다.
``follow: live``는 정본을 그대로 쓰고, ``follow: pinned``는 등록할 때의
해시(``pinned``)로 만든 ``cache/`` 사본을 쓴다.

이름 해석 순서:

1. 펜스가 ``@해시``를 주면 그 해시의 캐시 사본.
2. 프로젝트가 주어지면 ``<프로젝트>/.madang/viewers/*/``에서 같은 이름.
   그 프로젝트 안에서만 전역 등록보다 우선한다.
3. 전역 등록부.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from madang import config
from madang.store.files import atomic_write
from madang.viewers import pinning
from madang.viewers.manifest import (
    MANIFEST_FILE,
    Manifest,
    ViewerError,
    check_name,
    load_manifest,
)

FOLLOW_LIVE = "live"
FOLLOW_PINNED = "pinned"
FOLLOW_MODES = (FOLLOW_LIVE, FOLLOW_PINNED)

STATUS_OK = "ok"
# source 폴더(또는 pinned 사본)가 없거나 규격이 깨졌다.
STATUS_BROKEN = "broken"
# 어디에도 그 이름이 없다.
STATUS_MISSING = "missing"

ORIGIN_PROJECT = "project"
ORIGIN_REGISTRY = "registry"
ORIGIN_CACHE = "cache"


@dataclass(frozen=True)
class Registration:
    """등록부 항목 하나.

    Attributes:
        name: ``프로젝트/뷰어`` 이름.
        source: 뷰어 폴더의 절대 경로(정본).
        follow: ``live`` 또는 ``pinned``.
        pinned: ``pinned``일 때 사본의 해시.
    """

    name: str
    source: Path
    follow: str
    pinned: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """``viewers.yaml`` 항목 모양의 dict를 반환한다."""
        data: dict[str, Any] = {
            "name": self.name,
            "source": str(self.source),
            "follow": self.follow,
        }
        if self.pinned is not None:
            data["pinned"] = self.pinned
        return data


@dataclass(frozen=True)
class Resolved:
    """이름을 해석한 결과.

    Attributes:
        name: 요청한 뷰어 이름.
        status: ``ok``, ``broken``, ``missing``.
        origin: 찾은 곳(``project``, ``registry``, ``cache``). 못 찾으면 None.
        manifest: ``ok``일 때 뷰어 규격.
        pin: 캐시 사본을 쓸 때 그 해시.
        message: ``ok``가 아닐 때 이유.
    """

    name: str
    status: str
    origin: str | None = None
    manifest: Manifest | None = None
    pin: str | None = None
    message: str | None = None


class Registry:
    """앱 홈의 뷰어 등록부.

    Args:
        home: 앱 홈. ``config.resolve_home``과 같이 해석한다.
    """

    def __init__(self, home: str | Path | None = None) -> None:
        self.home = config.resolve_home(home)

    @property
    def path(self) -> Path:
        """``viewers.yaml`` 경로."""
        return self.home / config.VIEWERS_FILE

    def entries(self) -> list[Registration]:
        """등록 항목을 파일 순서대로 반환한다.

        Raises:
            ViewerError: 파일이 목록이 아니거나 항목이 틀렸다
                (``registry-invalid``).
        """
        if not self.path.is_file():
            return []
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ViewerError(
                "registry-invalid", f"{self.path}: {exc}"
            ) from exc
        if data is None:
            return []
        if not isinstance(data, list):
            raise ViewerError(
                "registry-invalid", f"{self.path}: expected a list of viewers"
            )
        found = [self._parse(i, item) for i, item in enumerate(data, 1)]
        _check_unique(found, self.path)
        return found

    def get(self, name: str) -> Registration:
        """이름으로 등록 항목을 찾는다.

        Raises:
            ViewerError: 등록되지 않았다(``not-found``).
        """
        for entry in self.entries():
            if entry.name == name:
                return entry
        raise ViewerError("not-found", f"viewer {name!r} is not registered")

    def register(
        self, source: str | Path, follow: str = FOLLOW_LIVE
    ) -> Registration:
        """뷰어 폴더를 ``viewer.json``의 이름으로 등록한다.

        ``pinned``면 지금 해시로 캐시 사본을 만든다.

        Args:
            source: 뷰어 폴더.
            follow: ``live`` 또는 ``pinned``.

        Returns:
            새 등록 항목.

        Raises:
            ViewerError: 규격이 틀렸거나(``manifest-*``, ``name-invalid``),
                같은 이름이 이미 있다(``name-conflict``).
        """
        _check_follow(follow)
        manifest = load_manifest(Path(source).expanduser())
        entries = self.entries()
        if any(e.name == manifest.name for e in entries):
            raise ViewerError(
                "name-conflict",
                f"viewer {manifest.name!r} is already registered",
            )
        pinned = None
        if follow == FOLLOW_PINNED:
            pinned = pinning.pin_viewer(
                self.home, manifest.folder, manifest.name
            )
        entry = Registration(manifest.name, manifest.folder, follow, pinned)
        self._save([*entries, entry])
        return entry

    def unregister(self, name: str) -> Registration:
        """등록을 지운다. 정본 폴더와 캐시 사본은 건드리지 않는다.

        Raises:
            ViewerError: 등록되지 않았다(``not-found``).
        """
        entry = self.get(name)
        self._save([e for e in self.entries() if e.name != name])
        return entry

    def repin(self, name: str) -> Registration:
        """고정(pinned) 항목을 정본의 지금 상태로 다시 고정한다.

        Raises:
            ViewerError: 등록되지 않았거나(``not-found``), pinned가
                아니거나(``not-pinned``), 정본이 없다(``source-missing``).
        """
        entry = self.get(name)
        if entry.follow != FOLLOW_PINNED:
            raise ViewerError("not-pinned", f"viewer {name!r} follows live")
        if self.status(entry) != STATUS_OK:
            raise ViewerError(
                "source-missing", f"{entry.source} is not a viewer folder"
            )
        pinned = pinning.pin_viewer(self.home, entry.source, name)
        updated = Registration(name, entry.source, entry.follow, pinned)
        self._save([updated if e.name == name else e for e in self.entries()])
        return updated

    def status(self, entry: Registration) -> str:
        """정본 폴더가 있으면 ``ok``, 없으면 ``broken``(끊김)."""
        if (entry.source / MANIFEST_FILE).is_file():
            return STATUS_OK
        return STATUS_BROKEN

    def resolve(
        self,
        name: str,
        *,
        project: Path | None = None,
        pin: str | None = None,
    ) -> Resolved:
        """문서가 부른 뷰어 이름을 쓸 폴더로 해석한다.

        Args:
            name: 뷰어 이름.
            project: 문서가 있는 프로젝트 폴더. 주면 그 프로젝트의
                ``.madang/viewers/``가 전역 등록보다 우선한다.
            pin: 펜스의 ``@해시``. 주면 그 해시의 캐시 사본만 쓴다.

        Returns:
            해석 결과. 못 찾거나 끊겼으면 상태에 이유가 있다.

        Raises:
            ViewerError: 이름이 틀렸거나(``name-invalid``), 프로젝트 안에
                같은 이름이 둘 있거나(``name-conflict``), 등록부가
                깨졌거나(``registry-invalid``), 해시 접두어가
                모호하다(``pin-ambiguous``).
        """
        check_name(name)
        if pin:
            return self._resolve_pin(name, pin)
        if project is not None:
            local = project_viewers(project).get(name)
            if local is not None:
                return Resolved(name, STATUS_OK, ORIGIN_PROJECT, local)
        for entry in self.entries():
            if entry.name == name:
                return self._resolve_entry(entry)
        return Resolved(
            name, STATUS_MISSING, message=f"viewer {name!r} is not registered"
        )

    def _resolve_pin(self, name: str, pin: str) -> Resolved:
        found = pinning.find_pinned(self.home, pin, name)
        if found is None:
            return Resolved(
                name,
                STATUS_BROKEN,
                ORIGIN_CACHE,
                pin=pin,
                message=f"no pinned copy {pin} of {name}",
            )
        return _loaded(name, ORIGIN_CACHE, found[1], found[0])

    def _resolve_entry(self, entry: Registration) -> Resolved:
        if entry.follow == FOLLOW_PINNED and entry.pinned:
            folder = pinning.cache_folder(self.home, entry.pinned, entry.name)
            return _loaded(entry.name, ORIGIN_CACHE, folder, entry.pinned)
        return _loaded(entry.name, ORIGIN_REGISTRY, entry.source, None)

    def _parse(self, index: int, item: object) -> Registration:
        where = f"{self.path}: item {index}"
        if not isinstance(item, dict):
            raise ViewerError(
                "registry-invalid", f"{where}: expected a mapping"
            )
        name, source = item.get("name"), item.get("source")
        follow, pinned = item.get("follow", FOLLOW_LIVE), item.get("pinned")
        if not isinstance(source, str) or not source:
            raise ViewerError(
                "registry-invalid", f"{where}: source is required"
            )
        try:
            check_name(name)
            _check_follow(follow)
        except ViewerError as exc:
            raise ViewerError("registry-invalid", f"{where}: {exc}") from exc
        if (follow == FOLLOW_PINNED) != isinstance(pinned, str):
            raise ViewerError(
                "registry-invalid",
                f"{where}: pinned is required exactly when follow is pinned",
            )
        return Registration(
            name, Path(source).expanduser(), follow, pinned or None
        )

    def _save(self, entries: list[Registration]) -> None:
        body = yaml.safe_dump(
            [e.to_dict() for e in entries],
            allow_unicode=True,
            sort_keys=False,
        )
        self.home.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, self._header() + body)

    def _header(self) -> str:
        """기존 파일(없으면 기본 파일)의 맨 앞 주석 줄을 유지한다."""
        text = (
            self.path.read_text(encoding="utf-8")
            if self.path.is_file()
            else config.default_text(config.VIEWERS_FILE)
        )
        lines = []
        for line in text.splitlines(keepends=True):
            if not line.startswith("#"):
                break
            lines.append(line)
        return "".join(lines)


def project_viewers(project: Path) -> dict[str, Manifest]:
    """프로젝트 ``.madang/viewers/`` 안의 뷰어를 이름별로 반환한다.

    규격이 틀린 폴더는 건너뛴다.

    Args:
        project: 프로젝트 폴더.

    Returns:
        이름에서 규격으로의 대응.

    Raises:
        ViewerError: 같은 이름이 둘 이상이다(``name-conflict``).
    """
    base = project / config.PROJECT_DIR / "viewers"
    found: dict[str, Manifest] = {}
    if not base.is_dir():
        return found
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        try:
            manifest = load_manifest(folder)
        except ViewerError:
            continue
        if manifest.name in found:
            raise ViewerError(
                "name-conflict",
                f"{found[manifest.name].folder} and {folder} are both "
                f"named {manifest.name!r}",
            )
        found[manifest.name] = manifest
    return found


def _loaded(name: str, origin: str, folder: Path, pin: str | None) -> Resolved:
    """폴더의 규격을 읽어 해석 결과를 만든다. 없거나 틀리면 끊김이다."""
    try:
        manifest = load_manifest(folder)
    except ViewerError as exc:
        return Resolved(name, STATUS_BROKEN, origin, pin=pin, message=str(exc))
    if manifest.name != name:
        return Resolved(
            name,
            STATUS_BROKEN,
            origin,
            pin=pin,
            message=f"{folder} is now named {manifest.name!r}",
        )
    return Resolved(name, STATUS_OK, origin, manifest, pin)


def _check_follow(follow: object) -> None:
    if follow not in FOLLOW_MODES:
        raise ViewerError(
            "follow-invalid",
            f"follow must be one of {', '.join(FOLLOW_MODES)}, got {follow!r}",
        )


def _check_unique(entries: list[Registration], path: Path) -> None:
    seen: set[str] = set()
    for entry in entries:
        if entry.name in seen:
            raise ViewerError(
                "name-conflict", f"{path}: {entry.name!r} is registered twice"
            )
        seen.add(entry.name)
