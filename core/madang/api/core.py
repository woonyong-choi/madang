"""API 요청이 함께 쓰는 core 상태: 앱 홈, 이벤트, 흐름, 러너 확인.

core는 앱 홈의 유일한 작성자다. 요청의 쓰기와 커밋은 ``lock`` 안에서
한다.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from madang import config
from madang.api import errors, events
from madang.api.availability import Availability, Probe, probe_cli
from madang.graph.nodes import RunnerFactory
from madang.runners import make_runner
from madang.store import blocks, git, pages, summary
from madang.store.home import is_initialized

PORT_FILE = "core.port"


class Core:
    """앱 홈 하나를 맡은 core.

    Attributes:
        home: 앱 홈.
        hub: 이벤트 전달.
        lock: 앱 홈 쓰기와 커밋을 차례로 하게 한다.
        make_runner: 러너 이름으로 러너를 만든다.
        availability: 러너 사용 가능 여부 캐시.
        port: 대기 중인 포트. ``serve``가 정한다.
    """

    def __init__(
        self,
        home: Path,
        *,
        runners: RunnerFactory | None = None,
        probe: Probe = probe_cli,
        core_url: str | None = None,
    ) -> None:
        from madang.api.flows import Flows

        self.home = config.resolve_home(home)
        self.hub = events.EventHub()
        self.lock = threading.RLock()
        self.make_runner: RunnerFactory = runners or functools.partial(
            make_runner, core_url=core_url
        )
        self.availability = Availability(
            probe,
            on_change=lambda result: self.hub.emit(
                events.RUNNER_AVAILABILITY, result
            ),
        )
        self.flows = Flows(self)
        self.port: int | None = None

    # 설정과 찾기

    @property
    def initialized(self) -> bool:
        """앱 홈이 초기화됐는지 여부."""
        return is_initialized(self.home)

    def config(self) -> config.Config:
        """앱 홈 설정을 새로 읽는다. 초기화 전에는 409.

        Raises:
            HttpError: 앱 홈이 초기화되지 않았거나 설정이 깨졌다.
        """
        if not self.initialized:
            raise errors.conflict(
                f"app home {self.home} is not initialized; POST /home first"
            )
        try:
            return config.load_config(self.home)
        except Exception as exc:
            raise errors.conflict(f"cannot load config: {exc}") from exc

    def page_dir(self, page_id: str) -> Path:
        """페이지 폴더를 반환한다.

        Raises:
            HttpError: 페이지가 없다(404). 초기화 전의 앱 홈에는 페이지가
                없다.
        """
        if not self.initialized:
            raise errors.not_found(
                f"page '{page_id}' not found; app home is not initialized"
            )
        try:
            return pages.find_page(self.home, page_id)
        except pages.PageNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc

    def rel(self, path: Path) -> str:
        """앱 홈 기준 상대 경로를 반환한다."""
        return path.resolve().relative_to(self.home.resolve()).as_posix()

    # 쓰기

    def commit(self, paths: Iterable[str | Path], message: str) -> str | None:
        """앱 홈의 ``paths`` 아래 변경을 커밋한다.

        Args:
            paths: 앱 홈 기준 경로 또는 절대 경로.
            message: 커밋 메시지.

        Returns:
            커밋 해시. 바뀐 것이 없으면 None.

        Raises:
            HttpError: git이 실패했다(409).
        """
        rels = [p if isinstance(p, str) else self.rel(p) for p in paths]
        try:
            return git.commit_changes(self.home, rels, message)
        except git.GitError as exc:
            raise errors.conflict(f"cannot commit the app home: {exc}") from exc

    def page_commit(self, page_dir: Path, message: str) -> str | None:
        """페이지 폴더의 변경을 ``[<page-id>] <message>``로 커밋한다.

        흐름이 이 페이지를 실행 중이면 커밋하지 않는다. 그 변경은 실행
        커밋에 들어간다.
        """
        if self.flows.busy(page_dir.name):
            return None
        return self.commit([page_dir], f"[{page_dir.name}] {message}")

    # 이벤트

    def announce_page(self, page_dir: Path, kind: str) -> None:
        """페이지 카드를 ``page.created`` 또는 ``page.updated``로 알린다."""
        card = summary.page_card(page_dir)
        self.hub.emit(
            kind, {"page": card}, space=card["space"], page=card["id"]
        )

    def announce_blocks(
        self, page_dir: Path, known: set[str], run: int | None = None
    ) -> set[str]:
        """``known``에 없는 page.md 블록을 ``block.added``로 알린다.

        Args:
            page_dir: 페이지 폴더.
            known: 이미 알린 블록 id.
            run: 이 블록들을 만든 실행.

        Returns:
            지금 page.md에 있는 블록 id.
        """
        order = [
            str(b)
            for b in pages.read_header(page_dir / "page.md").get("blocks") or []
        ]
        for block_id in order:
            if block_id in known:
                continue
            try:
                header = blocks.block_header(page_dir, block_id)
            except blocks.BlockNotFoundError:
                continue
            self.announce_block(page_dir, events.BLOCK_ADDED, header, run)
        return set(order)

    def announce_block(
        self,
        page_dir: Path,
        kind: str,
        header: dict[str, Any],
        run: int | None = None,
    ) -> None:
        """블록 이벤트 하나를 낸다."""
        self.hub.emit(
            kind,
            {"block": header},
            space=page_dir.parent.parent.name,
            page=page_dir.name,
            block=header["id"],
            run=run if run is not None else header.get("run"),
        )

    def announce_memory(
        self, layer: str, tokens: int, page_dir: Path | None = None
    ) -> None:
        """``memory.updated``를 낸다."""
        where: dict[str, Any] = {}
        if page_dir is not None:
            where = {
                "space": page_dir.parent.parent.name,
                "page": page_dir.name,
            }
        self.hub.emit(
            events.MEMORY_UPDATED, {"layer": layer, "tokens": tokens}, **where
        )

    # 앱 홈 바꾸기

    def write_port(self) -> None:
        """``<home>/core.port``에 현재 포트를 쓴다."""
        if self.port is None:
            return
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / PORT_FILE).write_text(f"{self.port}\n", encoding="utf-8")

    def remove_port(self) -> None:
        """이 core가 쓴 ``core.port``를 지운다(다른 포트면 그대로 둔다)."""
        path = self.home / PORT_FILE
        if self.port is None or not path.is_file():
            return
        if path.read_text(encoding="utf-8").strip() == str(self.port):
            path.unlink(missing_ok=True)

    def switch_home(self, home: Path) -> None:
        """다른 앱 홈을 쓰기 시작한다. ``core.port``도 옮긴다."""
        home = config.resolve_home(home)
        if home == self.home:
            return
        self.remove_port()
        self.home = home
        self.write_port()
