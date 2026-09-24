"""한 동작 체크리스트: 샘플 세 프로젝트로 core API와 실제 claude를 돌린다.

샘플(``samples/``)을 임시 폴더에 복사해 임시 앱 홈(``MADANG_HOME``)에
등록하고, ``madang serve``를 띄워 API로만 다음을 확인한다. 앱 홈 설정은
``madang init``이 만든 기본 config.yaml 그대로이며, 라우팅 단계의 모델만
체크리스트 모델로 바꾼다. 러너 인자·종류·규칙·한도는 덧대지 않는다.

1. 위키 노트에 요청 → 폴더 대상 게시 HTML에 새 내용.
2. 코드 프로젝트에 버그 수정 요청 → 선언된 테스트 통과 → 자동 머지 →
   page.md 결과 블록과 ledger에 기록.
3. 이력서 JSON 수정 → 앱 문서 탭 호스트(``app.html``)와 게시 페이지를 같은
   렌더러로 헤드리스 Chromium에서 그려 픽셀 비교.
4. core 재시작 뒤 세 페이지 기록이 API 조회로 같음.
5. 되돌리기로 (2)를 되감음(머지 전 트리, 원래 파일).

``MADANG_CORE_BIN``을 주면 저장소 core(uv) 대신 그 실행 파일로 core를 띄우고
CLI를 부른다(앱에 동봉한 PyInstaller core 확인용).

항목마다 PASS/FAIL과 근거, 호출마다의 입력 수치를 보고서(md)에 쓴다. 앱
화면을 거치는 확인은 디스플레이가 없으므로 not run으로 남긴다. git은 core의
``madang.git`` 모듈로만 읽는다.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from websockets.sync.client import connect

from madang import git
from madang.viewers import Registry, document_context

PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT RUN"
FLOW_POLL_SECONDS = 5.0
CORE_START_SECONDS = 60.0
# 설정하면 uv 대신 이 실행 파일(앱에 동봉한 core)로 madang 명령을 돌린다.
CORE_BIN_ENV = "MADANG_CORE_BIN"
# 문서 영역 스크린샷에서 다른 픽셀 비율의 상한.
PIXEL_RATIO_LIMIT = 0.001
TEST_COMMAND = "python3 -m unittest discover -s tests"
CODE_FILES = ("textstats.py", "tests/test_textstats.py")


# core 프로세스와 API


class ApiError(RuntimeError):
    """API가 기대하지 않은 상태 코드를 돌려줬다."""


class Core:
    """임시 앱 홈으로 ``madang serve``를 띄우고 API를 부른다.

    Attributes:
        repo: 저장소 루트.
        home: 임시 앱 홈.
        env: core 프로세스 환경.
        log_path: core 출력 파일.
        port: 지금 core가 듣는 포트.
    """

    def __init__(
        self, repo: Path, home: Path, env: dict[str, str], log_path: Path
    ) -> None:
        self.repo = repo
        self.home = home
        self.env = env
        self.log_path = log_path
        self.port = 0
        self._proc: subprocess.Popen[bytes] | None = None
        self.events: EventLog | None = None

    def madang(self, *args: str) -> str:
        """CLI 명령 하나를 실행하고 표준 출력을 돌려준다."""
        out = subprocess.run(
            [*self._madang(), *args],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()

    def start(self) -> None:
        """core를 띄우고 응답할 때까지 기다린 뒤 이벤트를 받기 시작한다."""
        self.port = _free_port()
        log = self.log_path.open("ab")
        self._proc = subprocess.Popen(
            [*self._madang(), "serve", "--port", str(self.port)],
            env=self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + CORE_START_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"core exited; see {self.log_path}")
            port_file = self.home / "core.port"
            if port_file.is_file():
                self.port = int(port_file.read_text().strip() or self.port)
                try:
                    self.call("GET", "/health")
                    break
                except (OSError, ApiError):
                    pass
            time.sleep(0.5)
        else:
            raise RuntimeError(f"core did not answer; see {self.log_path}")
        self.events = EventLog(self.port, self.home / "events.jsonl")

    def stop(self) -> None:
        """core를 SIGTERM으로 멈추고 끝나기를 기다린다."""
        if self.events is not None:
            self.events.close()
            self.events = None
        if self._proc is None or self._proc.poll() is not None:
            return
        os.killpg(self._proc.pid, signal.SIGTERM)
        try:
            self._proc.wait(30)
        except subprocess.TimeoutExpired:
            os.killpg(self._proc.pid, signal.SIGKILL)
            self._proc.wait()

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        expect: tuple[int, ...] = (200, 201, 202, 204),
    ) -> tuple[int, Any]:
        """API를 부르고 ``(상태 코드, JSON 본문)``을 돌려준다.

        Raises:
            ApiError: 상태 코드가 ``expect``에 없다.
        """
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}"
            + urllib.parse.quote(path, safe="/?=&"),
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        parsed = json.loads(raw) if raw else None
        if status not in expect:
            raise ApiError(f"{method} {path} -> {status}: {parsed}")
        return status, parsed

    def get(self, path: str) -> Any:
        """GET 본문."""
        return self.call("GET", path)[1]

    def _madang(self) -> list[str]:
        """``madang`` 명령. ``MADANG_CORE_BIN``이면 그 실행 파일을 쓴다."""
        if core_bin := self.env.get(CORE_BIN_ENV):
            return [core_bin]
        return [
            "uv",
            "run",
            "--quiet",
            "--project",
            str(self.repo / "core"),
            "madang",
        ]


class EventLog:
    """``/events`` WebSocket을 받아 목록과 파일에 쌓는다."""

    def __init__(self, port: int, path: Path) -> None:
        self.items: list[dict[str, Any]] = []
        self._path = path
        self._socket = connect(f"ws://127.0.0.1:{port}/events")
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def close(self) -> None:
        """연결을 닫는다."""
        self._socket.close()
        self._thread.join(5)

    def of(self, kind: str, **where: str) -> list[dict[str, Any]]:
        """``kind`` 이벤트 중 봉투 값(``page``, ``project``)이 맞는 것."""
        return [
            e
            for e in self.items
            if e["type"] == kind
            and all(e.get(key) == value for key, value in where.items())
        ]

    def _pump(self) -> None:
        with self._path.open("a", encoding="utf-8") as out:
            try:
                for frame in self._socket:
                    event = json.loads(frame)
                    self.items.append(event)
                    out.write(json.dumps(event, ensure_ascii=False) + "\n")
            except Exception:  # noqa: BLE001 - 닫힌 연결은 끝으로 본다.
                return


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# 결과


@dataclass
class Item:
    """체크리스트 항목 하나의 판정과 근거."""

    number: int
    title: str
    status: str = FAIL
    evidence: list[str] = field(default_factory=list)

    def note(self, line: str) -> None:
        """근거 한 줄을 더한다."""
        self.evidence.append(line)

    def judge(self, checks: dict[str, bool]) -> None:
        """모든 확인이 참이면 PASS. 확인마다 근거를 남긴다."""
        for name, ok in checks.items():
            self.note(f"{'ok' if ok else 'NG'}: {name}")
        self.status = PASS if all(checks.values()) else FAIL


@dataclass
class Run:
    """체크리스트 한 번의 공유 상태."""

    repo: Path
    work: Path
    model: str
    core: Core
    roots: dict[str, Path] = field(default_factory=dict)
    pages: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    code: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)


# 준비


def git_env(work: Path) -> dict[str, str]:
    """임시 git 설정(작성자, 서명 없음)을 쓰는 환경 변수."""
    config = work / "gitconfig"
    config.write_text(
        "[user]\n\tname = checklist\n\temail = checklist@localhost\n"
        "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
    )
    return {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}


def prepare(run: Run) -> None:
    """앱 홈을 만들고 core를 띄운 뒤 샘플을 등록하고 설정을 API로 넣는다."""
    core = run.core
    core.madang("init")
    core.start()
    for name in ("wiki", "code", "resume"):
        root = run.work / "projects" / name
        shutil.copytree(run.repo / "samples" / name, root)
        core.call("POST", "/projects", {"path": str(root), "id": name})
        run.roots[name] = root
    configure_model(run)
    core.call("POST", "/projects/code/git/init")
    core.call("POST", "/projects/code/git/stage", {})
    core.call("POST", "/projects/code/git/commit", {"message": "init sample"})
    publish_folder = {"auto_publish": True}
    project_config(core, "wiki", publish_folder, ["notes"])
    project_config(core, "resume", publish_folder, ["docs"])
    project_config(
        core,
        "code",
        {"auto_merge": {"require_tests": True, "test": TEST_COMMAND}},
    )
    viewer = run.repo / "templates" / "viewers" / "resume-basic"
    core.call("POST", "/viewers", {"source": str(viewer), "follow": "live"})


def configure_model(run: Run) -> None:
    """기본 routes 절에서 단계마다 모델만 체크리스트 모델로 바꾼다.

    체크리스트는 claude만 쓰므로 모델을 바꾼 단계의 러너도 claude다. 종류,
    규칙, 페이지 종류, 한도, 러너 인자는 기본값 그대로 둔다. 모델이
    비어 있으면 routes 절도 그대로 둔다.
    """
    if not run.model:
        return
    routes = yaml.safe_load(run.core.get("/config/routes")["text"])
    for kind, tiers in routes["tiers"].items():
        routes["tiers"][kind] = [
            {**tier, "runner": "claude", "model": run.model} for tier in tiers
        ]
    body = yaml.safe_dump(routes, allow_unicode=True, sort_keys=False)
    run.core.call("PUT", "/config/routes", {"text": body})


def project_config(
    core: Core,
    project: str,
    policy: dict[str, Any],
    include: list[str] | None = None,
) -> None:
    """프로젝트 ``config.yaml``을 API로 저장한다."""
    data: dict[str, Any] = {"track": False, "policy": policy}
    if include:
        data["publish"] = {"include": include, "target": "folder:site"}
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    core.call("PUT", f"/projects/{project}/config", {"text": text})


# 흐름


def new_page(run: Run, project: str, title: str, kind: str) -> str:
    """페이지를 만들고 id를 돌려준다."""
    _, page = run.core.call(
        "POST", f"/projects/{project}/pages", {"title": title, "kind": kind}
    )
    run.pages[project] = page["id"]
    return page["id"]


def send(run: Run, page: str, text: str, timeout: float) -> dict[str, Any]:
    """요청을 보내고 흐름이 끝나거나 멈출 때까지 기다린 뒤 페이지를 준다."""
    run.core.call("POST", f"/pages/{page}/messages", {"text": text})
    deadline = time.monotonic() + timeout
    while (detail := run.core.get(f"/pages/{page}"))["busy"]:
        if time.monotonic() > deadline:
            raise TimeoutError(f"flow on {page} still running after {timeout}s")
        time.sleep(FLOW_POLL_SECONDS)
    return detail


def ledger_header(core: Core, page: str) -> dict[str, Any]:
    """API로 읽은 ledger.md 머리부."""
    content = core.get(f"/pages/{page}/memory")["ledger"]["content"]
    return yaml.safe_load(content.split("---", 2)[1]) or {}


def outcome(item: Item, detail: dict[str, Any]) -> None:
    """흐름이 끝난 모습(실행 수, 결과, 멈춘 이유)을 근거로 남긴다."""
    runs = [
        f"{r['n']}:{r.get('kind')}/{r.get('result_status')}"
        for r in detail["runs"]
    ]
    item.note(f"page={detail['id']} status={detail['status']} runs={runs}")
    if detail.get("waiting"):
        item.note(
            f"waiting={json.dumps(detail['waiting'], ensure_ascii=False)}"
        )


def agent_blocks(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """page.md의 결과(agent) 블록."""
    return [b for b in detail["blocks"] if b.get("role") == "agent"]


# 항목


def check_wiki(run: Run, item: Item, timeout: float) -> None:
    """위키 노트 요청이 폴더 대상 게시에 반영되는지 본다."""
    root = run.roots["wiki"]
    marker = f"WIKI-{secrets.token_hex(4)}"
    page = new_page(run, "wiki", "텃밭 노트", "doc")
    detail = send(
        run,
        page,
        "notes/garden.md 노트 끝에 '## 가을 준비' 절을 새로 추가하고, 그 절에 "
        f"다음 문장을 그대로 한 줄로 넣어 줘: 마늘은 10월에 심는다 ({marker}). "
        "다른 파일은 고치지 않는다.",
        timeout,
    )
    outcome(item, detail)
    html = root / "site" / "notes" / "garden.html"
    status = run.core.get("/projects/wiki/publish")
    item.note(f"publish={json.dumps(status, ensure_ascii=False)[:400]}")
    last = status.get("latest") or {}
    item.judge(
        {
            f"notes/garden.md에 {marker}": marker
            in (root / "notes" / "garden.md").read_text(),
            f"게시 HTML {html.relative_to(root)}에 {marker}": html.is_file()
            and marker in html.read_text(),
            "게시 기록이 notes/garden.md를 담음": "notes/garden.md"
            in json.dumps(last),
            "publish.done 이벤트": bool(
                run.core.events.of("publish.done", page=page)
            ),
            "사람을 기다리지 않음": not detail.get("waiting"),
        }
    )


def check_code(run: Run, item: Item, timeout: float) -> None:
    """버그 수정 → 선언된 테스트 → 자동 머지 → 페이지 기록을 본다."""
    root, core = run.roots["code"], run.core
    before = core.get("/projects/code/git/log?limit=1")[0]["hash"]
    run.code = {
        "before": before,
        "tree": _tree(root, before),
        "files": {name: (root / name).read_bytes() for name in CODE_FILES},
        "baseline_tests": _tests(root),
    }
    item.note(
        f"머지 전 HEAD={before[:12]} 기준 테스트 종료 코드="
        f"{run.code['baseline_tests']}"
    )
    page = new_page(run, "code", "단어 수 버그", "code")
    detail = send(
        run,
        page,
        "textstats.py의 word_count가 공백이 여러 개 이어지거나 앞뒤에 공백이 "
        "있으면 틀린 값을 낸다. 버그를 고쳐 tests/의 테스트가 모두 통과하게 "
        "해 줘. 테스트 파일은 고치지 않는다.",
        timeout,
    )
    outcome(item, detail)
    head = core.get("/projects/code/git/log?limit=3")
    item.note(
        "log=" + "; ".join(f"{c['hash'][:12]} {c['subject']}" for c in head)
    )
    merges = [
        e["data"]
        for e in core.events.of("git.changed", project="code")
        if e["data"].get("action") == "merge"
    ]
    item.note(f"git.changed(merge)={merges}")
    n = max((r["n"] for r in detail["runs"]), default=0)
    run.code.update(page=page, n=n, merged=head[0]["hash"])
    ledger = ledger_header(core, page)
    item.note(
        f"ledger status={ledger.get('status')} owner={ledger.get('owner')}"
    )
    undo_log = root / ".madang" / "pages" / page / "runs" / f"{n}.undo.json"
    effects = json.loads(undo_log.read_text()) if undo_log.is_file() else {}
    kinds = [e.get("kind") for e in effects.get("effects", [])]
    item.note(f"runs/{n}.undo.json effects={kinds}")
    item.judge(
        {
            "기준 테스트는 실패": run.code["baseline_tests"] != 0,
            "머지 뒤 main에서 테스트 통과": _tests(root) == 0,
            "HEAD가 머지 커밋": len(_parents(root, "HEAD")) == 2,
            "머지 이벤트(git.changed)": bool(merges),
            "page.md 결과 블록": bool(agent_blocks(detail)),
            "ledger status done": ledger.get("status") == "done",
            "되돌리기 기록에 merge": "merge" in kinds,
            "사람을 기다리지 않음": not detail.get("waiting"),
        }
    )


def check_resume(run: Run, item: Item, timeout: float) -> None:
    """이력서 JSON 수정 뒤 앱 호스트와 게시 화면을 픽셀로 비교한다."""
    root = run.roots["resume"]
    title = "결제 플랫폼 리드 엔지니어"
    marker = f"RESUME-{secrets.token_hex(4)}"
    page = new_page(run, "resume", "이력서", "doc")
    detail = send(
        run,
        page,
        f"docs/resume.json 이력서 데이터에서 title을 '{title}'로 바꾸고, "
        "바다페이 경력의 highlights 맨 앞에 "
        f"'{marker} 정산 대사 자동화' 항목을 넣어 줘. 다른 파일은 고치지 "
        "않는다.",
        timeout,
    )
    outcome(item, detail)
    data = json.loads((root / "docs" / "resume.json").read_text())
    site = root / "site" / "docs" / "resume.html"
    result = capture(run, root, site, [title, marker])
    item.note(
        "capture="
        + json.dumps(
            {k: result[k] for k in ("document", "full", "expected", "settled")},
            ensure_ascii=False,
        )
    )
    item.note(
        f"스크린샷: {run.work / 'capture'} (app-*.png, site-*.png, *-diff.png)"
    )
    doc = result["document"]
    full = result["full"]
    if full["ratio"] > PIXEL_RATIO_LIMIT:
        run.notes.append(
            "창 전체 스크린샷은 다르다(다른 픽셀 비율 "
            f"{full['ratio']:.4%}, 크기 {full['sizes']})."
        )
    item.judge(
        {
            "resume.json title 변경": data.get("title") == title,
            "게시 HTML 있음": site.is_file(),
            "publish.done 이벤트": bool(
                run.core.events.of("publish.done", page=page)
            ),
            "뷰어 펜스가 ok로 풀림": result["views"] == ["ok"],
            "앱 호스트에 새 내용": all(
                v["app"] for v in result["expected"].values()
            ),
            "게시 화면에 새 내용": all(
                v["site"] for v in result["expected"].values()
            ),
            "문서 영역 크기 같음": doc["sameSize"],
            f"문서 영역 다른 픽셀 비율 {doc['ratio']:.4%} <= "
            f"{PIXEL_RATIO_LIMIT:.1%}": doc["ratio"] <= PIXEL_RATIO_LIMIT,
            "외부 요청 없음": not result["externalRequests"],
        }
    )


def capture(
    run: Run, root: Path, site: Path, expect: list[str]
) -> dict[str, Any]:
    """앱이 문서 탭에 넘길 값을 만들고 Node 캡처로 두 화면을 비교한다.

    view 펜스 context는 core ``document_context``(앱과 같은 규칙)로 만들고,
    앱 테마 토큰은 앱 기본 테마 값(``tokens.json``)을 앱처럼 더한다.
    """
    markdown = (root / "docs" / "resume.md").read_text()
    context = document_context(
        markdown,
        Registry(run.core.home),
        document_dir=root / "docs",
        project=root,
    )
    runtime = run.repo / "templates" / "_runtime"
    context["tokens"] = json.loads((runtime / "tokens.json").read_text())
    payload = {
        "markdown": markdown,
        "context": context,
        "base": (root / "docs").as_uri() + "/",
    }
    out = run.work / "capture"
    out.mkdir(exist_ok=True)
    payload_path = out / "payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False))
    here = Path(__file__).resolve().parent
    command = [
        "node",
        str(here / "capture.mjs"),
        "--app",
        str(runtime / "app.html"),
        "--payload",
        str(payload_path),
        "--site",
        str(site),
        "--out",
        str(out),
    ]
    for word in expect:
        command += ["--expect", word]
    done = subprocess.run(
        command, capture_output=True, text=True, check=True, cwd=here
    )
    result = json.loads(done.stdout)
    result["views"] = [v["status"] for v in context["views"].values()]
    return result


def check_restart(run: Run, item: Item) -> None:
    """core를 다시 띄운 뒤 세 페이지의 API 조회가 같은지 본다."""
    before = snapshot(run)
    run.snapshot = before
    run.core.stop()
    run.core.start()
    after = snapshot(run)
    item.note(f"페이지={list(before)} core 포트 재시작 후={run.core.port}")
    item.note("앱 재시작: not run(디스플레이 없음)")
    checks = {}
    for page, value in before.items():
        diffs = _diff(value, after.get(page), page)
        if diffs:
            item.note(f"{page} 다른 곳: {diffs[:8]}")
        runs = len(value["page"]["runs"])
        checks[
            f"{page} 동일(실행 {runs}개, 블록 {len(value['page']['blocks'])}개)"
        ] = not diffs
    item.judge(checks)


def snapshot(run: Run) -> dict[str, Any]:
    """세 페이지의 상세, 기억 세 층, 실행 기록을 API로 읽는다."""
    found = {}
    for page in run.pages.values():
        detail = run.core.get(f"/pages/{page}")
        found[page] = {
            "page": detail,
            "memory": run.core.get(f"/pages/{page}/memory"),
            "runs": [
                run.core.get(f"/pages/{page}/runs/{r['n']}")
                for r in detail["runs"]
            ],
        }
    return found


def check_undo(run: Run, item: Item) -> None:
    """(2)의 마지막 실행을 되돌려 머지 전 트리와 원래 파일로 가는지 본다."""
    root, code = run.roots["code"], run.code
    if not code.get("n"):
        item.note("(2)가 실행 기록을 남기지 않아 되돌릴 것이 없다")
        return
    page, n = code["page"], code["n"]
    _, undone = run.core.call(
        "POST", f"/pages/{page}/runs/{n}/undo", expect=(200, 409)
    )
    item.note(f"undo run {n} -> {json.dumps(undone, ensure_ascii=False)}")
    head = run.core.get("/projects/code/git/log?limit=2")
    item.note(
        "log=" + "; ".join(f"{c['hash'][:12]} {c['subject']}" for c in head)
    )
    same_files = {
        name: (root / name).read_bytes() == data
        for name, data in code["files"].items()
    }
    status = run.core.get("/projects/code/git/status")
    item.judge(
        {
            "되돌림 커밋 생김": bool((undone or {}).get("reverted")),
            f"HEAD 트리 == 머지 전 해시 {code['before'][:12]}의 트리": _tree(
                root, "HEAD"
            )
            == code["tree"],
            **{f"{name} 원래 내용": ok for name, ok in same_files.items()},
            "테스트가 다시 기준대로 실패": _tests(root)
            == code["baseline_tests"],
            "머지 커밋은 이력에 남음": git.is_ancestor(root, code["merged"]),
            "작업 트리 깨끗함": status["files"] == [],
        }
    )


# git·테스트 읽기


def _tree(root: Path, ref: str) -> str:
    return git.run(root, "rev-parse", f"{ref}^{{tree}}").stdout.strip()


def _parents(root: Path, ref: str) -> list[str]:
    line = git.run(root, "rev-list", "--parents", "-n", "1", ref).stdout
    return line.split()[1:]


def _tests(root: Path) -> int:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        TEST_COMMAND.split(),
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
    ).returncode


def _diff(a: Any, b: Any, path: str) -> list[str]:
    """두 JSON 값이 다른 경로."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [
            d
            for key in sorted(set(a) | set(b))
            for d in _diff(a.get(key), b.get(key), f"{path}.{key}")
        ]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [
            d
            for i, (x, y) in enumerate(zip(a, b, strict=True))
            for d in _diff(x, y, f"{path}[{i}]")
        ]
    return [] if a == b else [path]


# 입력 수치와 보고서


def input_rows(run: Run) -> list[str]:
    """페이지의 모든 실행에서 호출당 입력 추정과 사용량을 표 줄로 만든다."""
    rows = []
    for project, page in run.pages.items():
        detail = run.core.get(f"/pages/{page}")
        for ref in detail["runs"]:
            record = run.core.get(f"/pages/{page}/runs/{ref['n']}")
            parts = (record.get("input") or {}).get("parts") or {}
            usage = record.get("usage") or {}
            rows.append(
                f"| {project} | {ref['n']} | {record.get('kind')} | "
                f"{record.get('runner')}/{record.get('model')}/"
                f"{record.get('effort')} | "
                + " ".join(f"{k}={v}" for k, v in parts.items())
                + f" | {(record.get('input') or {}).get('total_est')} | "
                f"{usage.get('input')}/{usage.get('cached')}/"
                f"{usage.get('output')} | {record.get('result_status')} |"
            )
    return rows


def write_report(
    run: Run, items: list[Item], rows: list[str], path: Path
) -> None:
    """항목별 결과와 근거, 입력 수치, 관찰을 md로 쓴다."""
    head = git.run(run.repo, "rev-parse", "--short", "HEAD").stdout.strip()
    lines = [
        "# 한 동작 체크리스트 결과",
        "",
        f"- 시각: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 코드: {head} · 모델: claude/{run.model}",
        f"- 작업 폴더: {run.work} (앱 홈 {run.core.home})",
        f"- 픽셀 기준: 문서 영역(#madang-page) 다른 픽셀 비율 <= "
        f"{PIXEL_RATIO_LIMIT:.1%}, pixelmatch 색 허용 0.1, 창 1000x1400",
        "",
        "| # | 항목 | 결과 |",
        "|---|---|---|",
        *(f"| {i.number} | {i.title} | {i.status} |" for i in items),
        "| - | 앱 화면을 거치는 확인(문서 탭 WebView, 앱 재시작) | NOT RUN "
        "(디스플레이 없음) |",
        "",
    ]
    for i in items:
        lines += [f"## {i.number}. {i.title} — {i.status}", ""]
        lines += [f"- {line}" for line in i.evidence] + [""]
    lines += [
        "## 호출당 입력",
        "",
        "input.parts는 core가 조립 때 센 부분별 추정, 사용량은 러너가 알린 "
        "input/cached/output이다.",
        "",
        "| 프로젝트 | run | 종류 | 러너/모델/강도 | input.parts | total_est "
        "| 사용량 | 결과 |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## 관찰",
        "",
        *([f"- {note}" for note in run.notes] or ["- 없음"]),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def attempt(item: Item, step: Callable[[], None]) -> Item:
    """항목을 실행하고, 예외가 나면 FAIL과 그 이유를 남긴다."""
    try:
        step()
    except Exception as exc:  # noqa: BLE001 - 다음 항목은 이어 간다.
        item.status = FAIL
        item.note(f"예외: {exc!r}")
        item.note(traceback.format_exc(limit=3).strip().replace("\n", " / "))
    return item


def checks(run: Run, timeout: float) -> list[tuple[str, Callable]]:
    """항목 제목과 그 확인 함수, 체크리스트 순서대로."""
    return [
        (
            "위키 노트 요청 → 게시 웹 반영",
            lambda i: check_wiki(run, i, timeout),
        ),
        (
            "버그 수정 → 테스트 통과 → 자동 머지 → 페이지 기록",
            lambda i: check_code(run, i, timeout),
        ),
        (
            "이력서 JSON 수정 → 문서 탭 호스트 = 게시 화면",
            lambda i: check_resume(run, i, timeout),
        ),
        ("core 재시작 뒤 세 페이지 기록 동일", lambda i: check_restart(run, i)),
        ("되돌리기로 (2) 되감기", lambda i: check_undo(run, i)),
    ]


def run_all(
    run: Run, timeout: float, items: list[Item], rows: list[str]
) -> None:
    """준비한 뒤 항목을 차례로 확인한다. 준비가 실패하면 멈춘다."""
    ready = attempt(
        Item(0, "준비(core 시작, 샘플 등록, 설정)"), lambda: prepare(run)
    )
    if ready.evidence:
        items.append(ready)
        return
    for number, (title, step) in enumerate(checks(run, timeout), 1):
        item = Item(number, title)
        items.append(attempt(item, lambda s=step, i=item: s(i)))
        print(f"[{item.status}] {number}. {title}", flush=True)
    reading = attempt(
        Item(0, "입력 수치"), lambda: rows.extend(input_rows(run))
    )
    run.notes += [f"입력 수치를 읽지 못했다: {e}" for e in reading.evidence]


def main() -> int:
    """체크리스트를 돌리고 보고서를 쓴다.

    Returns:
        모든 항목이 PASS면 0, 아니면 1.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--flow-timeout", type=float, default=1800.0)
    args = parser.parse_args()

    repo, work = args.repo.resolve(), args.work.resolve()
    home = work / "home"
    os.environ.update(git_env(work))
    env = {
        **os.environ,
        "MADANG_HOME": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    run = Run(repo, work, args.model, Core(repo, home, env, work / "core.log"))
    items: list[Item] = []
    rows: list[str] = []
    try:
        run_all(run, args.flow_timeout, items, rows)
    finally:
        run.core.stop()
        write_report(run, items, rows, args.report)
        print(f"report: {args.report}")
    return 0 if items and all(i.status == PASS for i in items) else 1


if __name__ == "__main__":
    sys.exit(main())
