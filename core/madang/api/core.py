"""API 요청이 함께 쓰는 core 상태: 앱 홈, 이벤트, 흐름, 러너 확인, 실행 대상.

core는 페이지 기록(``<project>/.madang/``)과 앱 홈 설정의 유일한
작성자다. 요청의 쓰기는 ``lock`` 안에서 한다.
"""

from __future__ import annotations

import functools
import threading
from pathlib import Path
from typing import Any

from madang import config
from madang import runs as targets
from madang.api import errors, events
from madang.api.availability import Availability, Probe, probe_cli
from madang.api.launch import relay_run_event
from madang.graph.nodes import RunnerFactory
from madang.runners import make_runner
from madang.store import blocks, pages, projects, runs, summary
from madang.store.home import LegacyHomeError, check_layout, is_initialized

# 사용량 기록을 읽을 Claude Code·Codex 폴더.
CLAUDE_DIR = "~/.claude"
CODEX_DIR = "~/.codex"


class Core:
    """앱 홈 하나를 맡은 core.

    Attributes:
        home: 앱 홈.
        hub: 이벤트 전달.
        lock: 페이지와 설정 쓰기를 차례로 하게 한다.
        make_runner: 러너 이름으로 러너를 만든다.
        availability: 러너 사용 가능 여부 캐시.
        supervisor: core가 띄운 실행 대상 프로세스.
        claude_dir: 사용량 기록을 읽을 Claude Code 폴더.
        codex_dir: 사용량 기록을 읽을 Codex 폴더.
        port: 대기 중인 포트. ``serve``가 정한다.
    """

    def __init__(
        self,
        home: Path,
        *,
        runners: RunnerFactory | None = None,
        probe: Probe = probe_cli,
        core_url: str | None = None,
        claude_dir: Path | None = None,
        codex_dir: Path | None = None,
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
        self.supervisor = targets.Supervisor(
            lambda kind, payload: relay_run_event(self, kind, payload)
        )
        self.claude_dir = claude_dir or Path(CLAUDE_DIR).expanduser()
        self.codex_dir = codex_dir or Path(CODEX_DIR).expanduser()
        self.port: int | None = None

    # 설정과 찾기

    @property
    def initialized(self) -> bool:
        """앱 홈이 초기화됐는지 여부."""
        return is_initialized(self.home)

    def config(self) -> config.Config:
        """앱 홈 설정을 새로 읽는다. 초기화 전이나 예전 구조면 409.

        Raises:
            HttpError: 앱 홈이 초기화되지 않았거나, 예전 구조이거나, 설정이
                깨졌다.
        """
        try:
            check_layout(self.home)
        except LegacyHomeError as exc:
            raise errors.conflict(str(exc)) from exc
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

    def project(self, project_id: str) -> projects.Project:
        """등록한 프로젝트를 반환한다.

        Raises:
            HttpError: 프로젝트가 없다(404).
        """
        try:
            return projects.get(self.home, project_id)
        except FileNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc

    def project_of(self, page_dir: Path) -> projects.Project:
        """페이지 폴더를 가진 프로젝트를 반환한다.

        Raises:
            HttpError: 페이지가 등록한 프로젝트 밖에 있다(404).
        """
        try:
            return projects.owner(self.home, page_dir)
        except FileNotFoundError as exc:
            raise errors.not_found(str(exc)) from exc

    def active_run(self, page_dir: Path, *, in_run: bool) -> int | None:
        """실행 안에서 온 요청이 붙일 실행 번호.

        Args:
            page_dir: 페이지 폴더.
            in_run: 에이전트 실행 안에서 보낸 요청인지 여부. 사람이 보낸
                요청에는 흐름이 돌고 있어도 실행 번호를 붙이지 않는다.

        Returns:
            돌고 있는 실행 번호. 사람의 요청이거나 흐름이 없으면 None.
        """
        if not in_run or not self.flows.busy(page_dir.name):
            return None
        return runs.current(page_dir)

    # 이벤트

    def announce_page(self, page_dir: Path, kind: str) -> None:
        """페이지 카드를 ``page.created`` 또는 ``page.updated``로 알린다."""
        card = self.page_card(page_dir)
        self.hub.emit(
            kind, {"page": card}, project=card["project"], page=card["id"]
        )

    def page_card(self, page_dir: Path) -> dict[str, Any]:
        """페이지 카드(프로젝트 id 포함)를 반환한다."""
        return summary.page_card(page_dir, self.project_of(page_dir).id)

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
            project=self.project_of(page_dir).id,
            page=page_dir.name,
            block=header["id"],
            run=run if run is not None else header.get("run"),
        )

    def announce_git(
        self, project: str, folder: Path, action: str, **data: Any
    ) -> None:
        """``git.changed``를 낸다.

        Args:
            project: 프로젝트 id.
            folder: 바뀐 작업 트리.
            action: 바꾼 동작(``commit``, ``push`` 등).
            **data: 더 알릴 값(``commit`` 등).
        """
        self.hub.emit(
            events.GIT_CHANGED,
            {"folder": str(folder), "action": action, **data},
            project=project,
        )

    def announce_memory(
        self, layer: str, tokens: int, page_dir: Path | None = None
    ) -> None:
        """``memory.updated``를 낸다."""
        where: dict[str, Any] = {}
        if page_dir is not None:
            where = {
                "project": self.project_of(page_dir).id,
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
        (self.home / config.PORT_FILE).write_text(
            f"{self.port}\n", encoding="utf-8"
        )

    def remove_port(self) -> None:
        """이 core가 쓴 ``core.port``를 지운다(다른 포트면 그대로 둔다)."""
        path = self.home / config.PORT_FILE
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
