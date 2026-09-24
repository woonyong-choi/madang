import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from madang import config, runs
from madang.api.app import create_app
from madang.cli import app
from madang.cli_agent import client
from madang.store import pages, projects
from madang.store.home import init_home

runner = CliRunner()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve_command(port: int) -> str:
    return f"{sys.executable} -m http.server {port} --bind 127.0.0.1"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    (root / ".madang").mkdir(parents=True)
    (root / "public").mkdir()
    (root / "public" / "index.html").write_text("<h1>hi</h1>\n")
    return root


@pytest.fixture
def home(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    init_home(home)
    projects.add(home, project, project_id="site")
    monkeypatch.setenv("MADANG_HOME", str(home))
    monkeypatch.delenv("MADANG_PAGE", raising=False)
    return home


class Events:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict]] = []
        self.lock = threading.Lock()

    def __call__(self, kind: str, payload: dict) -> None:
        with self.lock:
            self.items.append((kind, payload))

    def kinds(self) -> list[str]:
        with self.lock:
            return [kind for kind, _ in self.items]

    def lines(self) -> list[str]:
        with self.lock:
            return [p["line"] for k, p in self.items if k == runs.RUN_OUTPUT]


# 선언


def test_declare_appends_and_keeps_comments(project: Path) -> None:
    path = config.project_config_path(project)
    path.write_text("# 프로젝트 설정\ntrack: false\n\npolicy:\n  deny: []\n")

    runs.declare(project, "사이트", "npm run dev", cwd="public")
    runs.declare(project, "api", "make serve", opens="http://localhost:8000")

    text = path.read_text()
    assert text.startswith("# 프로젝트 설정\ntrack: false\n")
    assert "policy:\n  deny: []" in text
    data = yaml.safe_load(text)
    assert data["runs"] == [
        {"name": "사이트", "cwd": "public", "command": "npm run dev"},
        {
            "name": "api",
            "command": "make serve",
            "opens": "http://localhost:8000",
        },
    ]
    assert [t.name for t in runs.targets(project)] == ["사이트", "api"]
    assert runs.find(project, "api").opens == "http://localhost:8000"


def test_declare_creates_config_file(project: Path) -> None:
    runs.declare(project, "a", "echo a")
    assert runs.targets(project)[0].command == "echo a"


@pytest.mark.parametrize(
    ("name", "command", "cwd", "match"),
    [
        ("dup", "echo", ".", "already declared"),
        (" ", "echo", ".", "must not be empty"),
        ("x", "", ".", "must not be empty"),
        ("x", "echo", "../out", "inside the project"),
        ("x", "echo", "/tmp", "inside the project"),
    ],
)
def test_declare_refuses(
    project: Path, name: str, command: str, cwd: str, match: str
) -> None:
    runs.declare(project, "dup", "echo dup")
    with pytest.raises(runs.RunsError, match=match):
        runs.declare(project, name, command, cwd=cwd)
    assert len(runs.targets(project)) == 1


def test_declare_needs_records_folder(tmp_path: Path) -> None:
    with pytest.raises(runs.RunsError, match="does not exist"):
        runs.declare(tmp_path, "a", "echo a")


def test_find_only_declared(project: Path) -> None:
    (project / "package.json").write_text('{"scripts": {"dev": "vite"}}')
    assert runs.targets(project) == []
    with pytest.raises(runs.RunsError, match="not declared"):
        runs.find(project, "dev")


# 프로세스


def test_output_lines_and_exit(project: Path) -> None:
    runs.declare(project, "hello", "echo one; echo two >&2; exit 3")
    events = Events()
    proc = runs.Process(runs.find(project, "hello"), project, events)
    proc.start()
    assert proc.wait(10) == 3
    assert events.lines() == ["one", "two"]
    assert events.kinds()[0] == runs.RUN_STARTED
    assert events.kinds()[-1] == runs.RUN_EXITED
    assert not proc.running
    assert proc.wait_opens() is False


def test_start_refuses_missing_cwd(project: Path) -> None:
    runs.declare(project, "gone", "echo", cwd="nowhere")
    proc = runs.Process(runs.find(project, "gone"), project)
    with pytest.raises(runs.RunsError, match="does not exist"):
        proc.start()


def test_serve_opens_observe_ports_and_stop(project: Path) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    runs.declare(project, "site", serve_command(port), cwd="public", opens=url)
    events = Events()
    supervisor = runs.Supervisor(events)

    proc = supervisor.start(project, "site")
    try:
        assert proc.wait_opens(timeout=20)
        assert (runs.RUN_OPEN) in events.kinds()
        opened = [p for k, p in events.items if k == runs.RUN_OPEN]
        assert opened[0]["url"] == url
        ports = supervisor.ports(project, "site")
        assert port in [listen.port for listen in ports]
        with pytest.raises(runs.RunsError, match="already running"):
            supervisor.start(project, "site")
    finally:
        supervisor.stop(project, "site")

    assert not proc.running
    assert proc.ports() == []
    assert runs.listening_ports(proc.pid) == []
    assert events.kinds()[-1] == runs.RUN_STOPPED


def test_stop_kills_whole_tree(project: Path) -> None:
    runs.declare(project, "tree", "sleep 60 & sleep 60 & wait")
    proc = runs.Process(runs.find(project, "tree"), project)
    proc.start()
    time.sleep(0.3)
    assert proc.pid is not None
    proc.stop(timeout=5)
    with pytest.raises(ProcessLookupError):
        os.killpg(proc.pid, 0)


def test_stop_escalates_to_kill(project: Path) -> None:
    runs.declare(project, "stubborn", "trap '' TERM; sleep 60 & wait")
    proc = runs.Process(runs.find(project, "stubborn"), project)
    proc.start()
    time.sleep(0.3)
    assert proc.stop(timeout=0.5) == -signal.SIGKILL


def test_restart_runs_again(project: Path) -> None:
    runs.declare(project, "loop", "sleep 60")
    supervisor = runs.Supervisor()
    first = supervisor.start(project, "loop")
    second = supervisor.restart(project, "loop")
    try:
        assert not first.running
        assert second.running
        assert first.pid != second.pid
    finally:
        supervisor.stop_all()
    assert supervisor.running() == []


def test_supervisor_refuses_unknown(project: Path) -> None:
    supervisor = runs.Supervisor()
    with pytest.raises(runs.RunsError, match="not declared"):
        supervisor.start(project, "nope")
    with pytest.raises(runs.RunsError, match="not been started"):
        supervisor.stop(project, "nope")


def test_declare_refuses_symlink_out_of_project(
    project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(runs.RunsError, match="inside the project"):
        runs.declare(project, "x", "echo", cwd="link")
    target = config.RunTarget(name="x", command="echo", cwd="link")
    with pytest.raises(runs.RunsError, match="inside the project"):
        runs.Process(target, project).start()


# 명령줄(core API 경유)


@pytest.fixture
def core(home: Path, monkeypatch: pytest.MonkeyPatch):
    """명령이 부를 core를 같은 프로세스에 띄운다."""
    api = create_app(home)

    def transport(method: str, path: str, payload):
        response = http.request(method, path, json=payload)
        body = response.json() if response.content else None
        return response.status_code, body

    with TestClient(api, base_url="http://127.0.0.1:7470") as http:
        monkeypatch.setattr(client, "open_transport", lambda _home: transport)
        yield api.state.core
    api.state.core.supervisor.stop_all()


def test_cli_add_and_list(core, project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "runs",
            "add",
            "--project",
            "site",
            "--name",
            "site",
            "--cwd",
            "public",
            "--command",
            "python -m http.server",
            "--opens",
            "http://localhost:8000",
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["runs", "list", "--project", "site"])
    assert result.exit_code == 0, result.output
    assert result.output == (
        "site\tpublic\tpython -m http.server\thttp://localhost:8000\tstopped\n"
    )


def test_cli_uses_page_project(
    core, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = pages.create_page(project / ".madang" / "pages", "build")
    monkeypatch.setenv("MADANG_PAGE", page.name)
    result = runner.invoke(
        app, ["runs", "add", "--name", "a", "--command", "echo a"]
    )
    assert result.exit_code == 0, result.output
    assert runs.find(project, "a").command == "echo a"


def test_cli_refuses(core, project: Path) -> None:
    result = runner.invoke(app, ["runs", "list"])
    assert result.exit_code == 1
    assert "--project" in result.output
    args = ["--project", "site", "--name", "a", "--command", "x", "--cwd", ".."]
    result = runner.invoke(app, ["runs", "add", *args])
    assert result.exit_code == 1
    assert "inside the project" in result.output
    result = runner.invoke(app, ["runs", "start", "nope", "--project", "site"])
    assert result.exit_code == 1
    assert "not declared" in result.output
    runs.declare(project, "idle", "sleep 60")
    result = runner.invoke(app, ["runs", "stop", "idle", "--project", "site"])
    assert result.exit_code == 1
    assert "not running" in result.output


def test_cli_start_is_checked_by_policy(core, project: Path) -> None:
    runs.declare(project, "danger", "git push --force origin main")
    result = runner.invoke(
        app, ["runs", "start", "danger", "--project", "site"]
    )
    assert result.exit_code == 1
    assert "push --force" in result.output
    assert core.supervisor.running() == []


def test_cli_start_opens_then_stop(core, project: Path) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    runs.declare(project, "site", serve_command(port), opens=url)
    result = runner.invoke(app, ["runs", "start", "site", "--project", "site"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("시작: site (pid ")
    proc = core.supervisor.get(project, "site")
    assert proc.wait_opens(timeout=20)
    result = runner.invoke(app, ["runs", "list", "--project", "site"])
    assert result.output.rstrip().endswith("running")
    result = runner.invoke(app, ["runs", "stop", "site", "--project", "site"])
    assert result.exit_code == 0, result.output
    assert result.output == "정지: site\n"
    assert not proc.running
    assert not runs.process.responds(url)
