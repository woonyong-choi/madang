"""core API 클라이언트: 에이전트 명령이 core에 변경을 요청한다.

페이지 파일은 core만 쓴다. 이 모듈은 HTTP 요청만 보낸다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from madang import config

CORE_URL_ENV = "MADANG_CORE_URL"
DEFAULT_URL = "http://127.0.0.1:7470"
TIMEOUT_SECONDS = 300

# (메서드, 경로, JSON 본문 또는 None) -> (상태 코드, 응답 JSON 또는 None)
Transport = Callable[[str, str, Any], tuple[int, Any]]


class CoreUnreachableError(Exception):
    """core에 연결할 수 없다."""


class RejectedError(Exception):
    """core가 요청을 거절했다.

    Attributes:
        status: HTTP 상태 코드.
        issues: 검증 문제(``code``, ``message``, ``line``, ``path``).
    """

    def __init__(
        self, status: int, message: str, issues: list[dict[str, Any]]
    ) -> None:
        super().__init__(message)
        self.status = status
        self.issues = issues


def core_url(home: Path | None) -> str:
    """코어 주소를 정한다.

    ``MADANG_CORE_URL``, ``<home>/core.port``, 기본 주소 순으로 찾는다.

    Args:
        home: ``--home``으로 받은 앱 홈. 없으면 환경 변수와 기본 위치.

    Returns:
        core의 기준 URL. 끝에 ``/``가 없다.
    """
    if url := os.environ.get(CORE_URL_ENV):
        return url.rstrip("/")
    port_file = config.resolve_home(home) / config.PORT_FILE
    try:
        port = int(port_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return DEFAULT_URL
    return f"http://127.0.0.1:{port}"


def http_transport(base_url: str) -> Transport:
    """``base_url``의 core로 HTTP 요청을 보내는 전송을 만든다."""

    def send(method: str, path: str, payload: Any) -> tuple[int, Any]:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _json(exc.read())
        except OSError as exc:
            raise CoreUnreachableError(
                f"core({base_url})에 연결할 수 없다: {exc}. "
                "madang serve로 core를 먼저 띄운다"
            ) from exc

    return send


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def open_transport(home: Path | None) -> Transport:
    """앱 홈에 맞는 core로 보내는 전송을 연다. 테스트가 바꿔 끼운다."""
    return http_transport(core_url(home))


def call(
    transport: Transport, method: str, path: str, payload: Any = None
) -> Any:
    """core에 요청을 보내고 응답 JSON을 반환한다.

    Raises:
        RejectedError: core가 4xx·5xx로 답했다.
        CoreUnreachableError: core에 연결할 수 없다.
    """
    status, body = transport(method, path, payload)
    if status >= 400:
        raise _rejection(status, body)
    return body


def quoted(segment: str) -> str:
    """경로 조각 하나를 URL에 넣을 수 있게 인코딩한다."""
    return quote(segment, safe="")


class CoreClient:
    """페이지 하나에 대한 core API 호출.

    Attributes:
        page: 페이지 id.
    """

    def __init__(self, transport: Transport, page: str) -> None:
        self._send = transport
        self.page = page

    def _call(self, method: str, path: str, payload: Any = None) -> Any:
        return call(self._send, method, path, payload)

    def _page_path(self, tail: str = "") -> str:
        return f"/pages/{quoted(self.page)}{tail}"

    def project(self) -> str:
        """페이지가 속한 프로젝트 id."""
        return self._call("GET", self._page_path())["project"]

    def _project_path(self, tail: str) -> str:
        return f"/projects/{quoted(self.project())}{tail}"

    def set_task(
        self,
        task_id: str,
        status: str,
        title: str | None,
        due: str | None,
    ) -> dict[str, Any]:
        """태스크를 추가하거나 갱신하고 결과 태스크를 반환한다."""
        payload = {"id": task_id, "status": status}
        if title is not None:
            payload["title"] = title
        if due is not None:
            payload["due"] = due
        return self._call("PATCH", self._page_path("/ledger/tasks"), payload)

    def decide(self, decision: dict[str, Any]) -> dict[str, Any]:
        """결정을 기록하고 저장된 결정을 반환한다."""
        return self._call(
            "POST", self._page_path("/ledger/decisions"), decision
        )

    def add_artifact(self, path: str) -> list[str]:
        """산출물을 등록하고 전체 산출물 목록을 반환한다."""
        return self._call(
            "POST", self._page_path("/ledger/artifacts"), {"path": path}
        )

    def commit(self, message: str, *, in_run: bool = False) -> str:
        """페이지의 작업 트리를 커밋하고 커밋 해시를 반환한다.

        페이지에 워크트리가 있으면 core가 그 워크트리에 커밋한다.
        ``in_run``이 참이면 진행 중인 실행의 되돌리기 기록에 남긴다.
        """
        payload = {"message": message, "page": self.page, "in_run": in_run}
        result = self._call("POST", self._project_path("/repo/commit"), payload)
        return result["commit"]

    def push(self) -> dict[str, Any]:
        """페이지 작업 트리의 현재 브랜치를 푸시한다.

        Returns:
            ``branch``, ``remote``.
        """
        return self._call(
            "POST", self._project_path("/repo/push"), {"page": self.page}
        )

    def create_view(
        self,
        template: str,
        data: list[str],
        title: str | None,
        *,
        in_run: bool = False,
    ) -> dict[str, Any]:
        """뷰 블록을 만들고 블록 머리부를 반환한다.

        ``in_run``이 참이면 진행 중인 실행이 만든 블록으로 기록한다.
        """
        name = template.partition("@")[0]
        payload: dict[str, Any] = {
            "type": "view",
            "name": name,
            "template": template,
            "data": data,
            "in_run": in_run,
        }
        if title:
            payload["title"] = title
        return self._call("POST", self._page_path("/blocks"), payload)


def _rejection(status: int, body: Any) -> RejectedError:
    if not isinstance(body, dict):
        return RejectedError(status, f"core가 {status}로 답했다", [])
    message = str(body.get("message") or f"core가 {status}로 답했다")
    issues = [
        i
        for i in body.get("issues") or []
        if not (
            i.get("code") == "invalid-value" and i.get("message") == message
        )
    ]
    return RejectedError(status, message, issues)
