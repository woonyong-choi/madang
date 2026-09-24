"""API 테스트 도우미: 계약 검사기, 가짜 러너, 앱 픽스처."""

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from madang.api.app import create_app
from madang.api.contract import contract_document
from madang.runners.base import RunEvent, RunResult, Usage
from madang.store import frontmatter, pages, projects
from madang.store.home import init_home

STREAMS = Path(__file__).parent / "fixtures" / "streams"
URN = "urn:madang:contract"
LOCAL = "http://127.0.0.1:7470"
WS = "ws://127.0.0.1:7470"
PROJECT = "work"


def _pointer(*parts: str) -> str:
    return "".join("/" + p.replace("~", "~0").replace("/", "~1") for p in parts)


class Contract:
    """openapi.yaml로 응답과 이벤트를 검사한다."""

    def __init__(self) -> None:
        self.doc = contract_document()
        resource = Resource.from_contents(
            self.doc, default_specification=DRAFT202012
        )
        self.registry = Registry().with_resource(URN, resource)
        self.paths = [
            (re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$"), p)
            for p in self.doc["paths"]
        ]

    def validate(self, pointer: str, value: Any) -> None:
        """``pointer``의 스키마로 ``value``를 검사한다."""
        validator = Draft202012Validator(
            {"$ref": f"{URN}#{pointer}"}, registry=self.registry
        )
        problems = sorted(validator.iter_errors(value), key=str)
        assert not problems, "\n".join(
            f"{list(p.absolute_path)}: {p.message}" for p in problems[:5]
        )

    def event(self, event: dict[str, Any]) -> None:
        """WebSocket 이벤트 하나를 ``Event`` 스키마로 검사한다."""
        self.validate("/components/schemas/Event", event)

    def operation(self, method: str, path: str) -> tuple[str, dict]:
        """구체 경로에 맞는 계약 경로와 연산을 찾는다."""
        for pattern, template in self.paths:
            if pattern.match(path) and method in self.doc["paths"][template]:
                return template, self.doc["paths"][template][method]
        raise AssertionError(f"{method.upper()} {path} is not in the contract")

    def check(self, response: Any, status: int | None = None) -> Any:
        """응답의 상태와 본문이 계약과 맞는지 보고 본문을 반환한다."""
        if status is not None:
            assert response.status_code == status, response.text
        method = response.request.method.lower()
        raw = response.request.url.raw_path.decode().split("?", 1)[0]
        template, op = self.operation(method, raw)
        code = str(response.status_code)
        assert code in op["responses"], (
            f"{method.upper()} {template} answered {code}: {response.text}"
        )
        spec = op["responses"][code]
        base = _pointer("paths", template, method, "responses", code)
        if "$ref" in spec:
            name = spec["$ref"].rsplit("/", 1)[-1]
            spec = self.doc["components"]["responses"][name]
            base = _pointer("components", "responses", name)
        content = spec.get("content", {}).get("application/json")
        if content is None:
            assert not response.content, response.text
            return None
        body = response.json()
        self.validate(
            base + _pointer("content", "application/json", "schema"), body
        )
        return body


# 가짜 러너


def set_status(status: str):
    """ledger.md의 status를 바꾸는 에이전트 동작."""

    def act(page_dir: Path) -> None:
        state = page_dir / "ledger.md"
        header, body = frontmatter.read(state)
        header["status"] = status
        state.write_text(frontmatter.dumps(header, body))

    return act


class Script:
    """러너 호출 순서대로 에이전트 동작을 내준다."""

    def __init__(self, *acts: Any) -> None:
        self.acts = list(acts)
        self.calls: list[dict] = []
        self.gate: Any = None

    def runner(self, name: str, cfg: Any) -> "FakeRunner":
        return FakeRunner(name, self)


class FakeRunner:
    """러너 이름에 맞는 스트림 기록을 남기고 동작 하나를 실행한다."""

    def __init__(self, name: str, script: Script) -> None:
        self.name = name
        self.script = script
        self.cancelled = False

    def exec(self, **kw: Any) -> RunResult:
        page_dir = kw["events_log"].parent.parent
        self.script.calls.append({**kw, "name": self.name})
        kw["events_log"].write_text(
            (STREAMS / f"{self.name}-tools.jsonl").read_text()
        )
        kw["on_event"](RunEvent("text", text="working"))
        if self.script.gate is not None:
            self.script.gate(self)
        if self.cancelled:
            return RunResult(status="cancelled", error="cancelled")
        status = self.script.acts.pop(0)(page_dir) or "done"
        return RunResult(
            status=status,
            usage=Usage(input=100, cached=10, output=5),
            final_text=f"ANSWER-{len(self.script.calls)}",
            duration=0.1,
            error=None if status == "done" else "boom",
        )

    def cancel(self) -> None:
        self.cancelled = True


# 픽스처


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("MADANG_BY", raising=False)
    monkeypatch.delenv("MADANG_TEMPLATES", raising=False)
    monkeypatch.delenv("MADANG_PAGE", raising=False)


@pytest.fixture(scope="session")
def contract() -> Contract:
    return Contract()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """``work`` 프로젝트 하나를 등록한 앱 홈."""
    root = tmp_path / "home"
    init_home(root)
    (tmp_path / PROJECT).mkdir()
    projects.add(root, tmp_path / PROJECT, project_id=PROJECT)
    return root


@pytest.fixture
def project_root(home: Path) -> Path:
    return projects.get(home, PROJECT).root


@pytest.fixture
def script() -> Script:
    return Script()


@pytest.fixture
def client(home: Path, script: Script):
    # 사용량은 실제 기록 대신 비어 있는 임시 폴더를 읽는다.
    app = create_app(
        home,
        runners=script.runner,
        probe=lambda name, spec: None,
        claude_dir=home / "no-claude",
        codex_dir=home / "no-codex",
    )
    with TestClient(app, base_url=LOCAL) as test_client:
        yield test_client


@pytest.fixture
def page(client: TestClient) -> str:
    response = client.post(
        f"/projects/{PROJECT}/pages", json={"title": "이력서"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def page_dir(home: Path, page_id: str) -> Path:
    return pages.find_page(home, page_id)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
