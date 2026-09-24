from pathlib import Path

import pytest
from typer.testing import CliRunner

from madang import __version__
from madang.cli import app
from madang.config import (
    ConfigError,
    MadangConfig,
    RoutesConfig,
    load_config,
    load_project_config,
    resolve_home,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """사용자·시스템 git 설정(서명, 훅 등)이 테스트에 섞이지 않게 한다."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def test_init_creates_home(home: Path) -> None:
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output

    assert sorted(p.name for p in home.iterdir()) == [
        "cache",
        "config.yaml",
        "profile.md",
        "viewers.yaml",
    ]
    assert (home / "cache").is_dir()
    assert not (home / ".git").exists()
    assert "4 files" in result.output
    settings = (home / "config.yaml").read_text()
    assert "projects: []" in settings
    assert "\nroutes:\n" in settings and "\nrunners:\n" in settings
    assert (home / "profile.md").read_text().startswith("# Profile")


def test_init_is_idempotent(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    profile = home / "profile.md"
    profile.write_text("my notes\n")

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "already initialized" in result.output
    assert profile.read_text() == "my notes\n"


def test_init_restores_missing_file(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    (home / "profile.md").unlink()

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "1 files" in result.output
    assert (home / "profile.md").is_file()


@pytest.mark.parametrize(
    ("old", "hint"),
    [
        ("config/madang.yaml", "merge config/madang.yaml"),
        ("root.md", "rename root.md"),
    ],
)
def test_init_refuses_old_settings(home: Path, old: str, hint: str) -> None:
    (home / old).parent.mkdir(parents=True, exist_ok=True)
    (home / old).write_text("x: 1\n")
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 1
    assert "old app home layout" in result.output
    assert hint in " ".join(result.output.split())
    assert not (home / "config.yaml").exists()


def test_old_home_with_new_file_is_refused(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    (home / "root.md").write_text("old\n")
    refused = runner.invoke(app, ["project", "list", "--home", str(home)])
    assert refused.exit_code == 1
    assert "profile.md" in refused.output


def test_init_refuses_old_layout(home: Path) -> None:
    (home / "spaces/root/pages").mkdir(parents=True)
    (home / "config").mkdir()
    (home / "config/madang.yaml").write_text("home_remote: null\n")
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 1
    assert "old app home layout" in result.output
    assert not (home / "profile.md").exists()
    for args in (
        ["project", "list"],
        ["page", "new", "--title", "x", "--project", "p"],
    ):
        refused = runner.invoke(app, [*args, "--home", str(home)])
        assert refused.exit_code == 1
        assert "old app home layout" in refused.output


def test_init_rejects_file_home(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("x")
    result = runner.invoke(app, ["init", "--home", str(target)])
    assert result.exit_code == 1
    assert "error:" in result.output


def test_load_config(home: Path) -> None:
    runner.invoke(app, ["init", "--home", str(home)])
    cfg = load_config(home)
    assert cfg.home == home.resolve()
    assert cfg.madang.core.port == 7470
    assert cfg.madang.core.bind == "127.0.0.1"
    assert cfg.madang.limits.ledger_tokens == 2000
    assert cfg.madang.limits.run_timeout_minutes["design"] == 30
    assert cfg.madang.projects == []
    assert cfg.routes.default_kind == "build"
    assert "review" in cfg.routes.kinds
    assert cfg.routes.tiers["design"][0].runner == "claude"
    assert cfg.routes.limits.blocked_after_failures == 2
    assert cfg.routes.decider.min_confidence == 0.7
    assert cfg.runners["claude"].bin == "claude"
    assert cfg.runners["codex"].args[0] == "exec"


def test_model_defaults_match_bundled(home: Path) -> None:
    runner.invoke(app, ["init", "--home", str(home)])
    cfg = load_config(home)
    assert MadangConfig() == cfg.madang
    bare = RoutesConfig(
        kinds=cfg.routes.kinds, default_kind=cfg.routes.default_kind
    )
    assert bare.limits == cfg.routes.limits
    assert bare.decider == cfg.routes.decider


def test_load_config_reads_home_files(home: Path) -> None:
    runner.invoke(app, ["init", "--home", str(home)])
    path = home / "config.yaml"
    path.write_text(path.read_text().replace("port: 7470", "port: 7480"))
    assert load_config(home).madang.core.port == 7480


def test_missing_sections_use_bundled_defaults(home: Path) -> None:
    home.mkdir()
    (home / "config.yaml").write_text("core:\n  port: 7490\n")
    cfg = load_config(home)
    assert cfg.madang.core.port == 7490
    assert cfg.routes.default_kind == "build"
    assert cfg.runners["codex"].bin == "codex"


@pytest.mark.parametrize(
    ("text", "where"),
    [
        ("core:\n  port: nope\n", ":2: core.port: "),
        (
            "routes:\n  kinds: [build]\n  default_kind: build\n"
            "  tiers:\n    build:\n      - {runner: claude}\n",
            ":6: routes.tiers.build.0.model: Field required",
        ),
        ("runners:\n  claude:\n    args: []\n", ":2: runners.claude.bin: "),
        ("runners: [claude]\n", ":1: runners: must be a mapping"),
        ("core: [\n", "invalid YAML"),
        ("- a\n", "(top): must be a mapping"),
    ],
)
def test_config_errors_point_at_the_place(
    home: Path, text: str, where: str
) -> None:
    home.mkdir()
    (home / "config.yaml").write_text(text)
    with pytest.raises(ConfigError) as caught:
        load_config(home)
    assert str(home.resolve() / "config.yaml") in str(caught.value)
    assert where in str(caught.value)
    result = runner.invoke(app, ["project", "list", "--home", str(home)])
    assert result.exit_code == 1
    assert where in result.output


def test_project_config_defaults(tmp_path: Path) -> None:
    cfg = load_project_config(tmp_path)
    assert cfg.track is False
    assert cfg.runs == [] and cfg.viewers == {}
    assert cfg.policy.auto_merge.require_tests is True
    assert cfg.policy.auto_merge.require_no_conflict is True
    assert cfg.policy.auto_publish is False
    assert cfg.publish.include == [] and cfg.publish.target is None


def test_project_config_is_read(tmp_path: Path) -> None:
    (tmp_path / ".madang").mkdir()
    (tmp_path / ".madang/config.yaml").write_text(
        """\
track: true
runs:
  - name: 이력서 사이트
    cwd: resume/site
    command: npm run dev
    opens: http://localhost:5173
policy:
  auto_merge: {require_tests: true, require_no_conflict: true, test: pytest}
  auto_publish: true
  deny: ["push --force", "reset --hard"]
publish:
  include: [docs/]
  target: gh-pages
viewers:
  resume/basic: /abs/viewers/resume
"""
    )
    cfg = load_project_config(tmp_path)
    assert cfg.track is True
    assert cfg.runs[0].name == "이력서 사이트"
    assert cfg.runs[0].opens == "http://localhost:5173"
    assert cfg.policy.auto_merge.test == "pytest"
    assert cfg.policy.deny == ["push --force", "reset --hard"]
    assert cfg.publish.target == "gh-pages"
    assert cfg.viewers == {"resume/basic": "/abs/viewers/resume"}


@pytest.mark.parametrize(
    ("text", "where"),
    [
        ("track: maybe\n", ":1: track: "),
        ("runs:\n  - name: dev\n", ":2: runs.0.command: Field required"),
        ("policy:\n  auto_merj: {}\n", ":2: policy.auto_merj: Extra inputs"),
    ],
)
def test_project_config_errors_point_at_the_place(
    tmp_path: Path, text: str, where: str
) -> None:
    (tmp_path / ".madang").mkdir()
    (tmp_path / ".madang/config.yaml").write_text(text)
    with pytest.raises(ConfigError, match=where):
        load_project_config(tmp_path)


def test_resolve_home_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MADANG_HOME", str(tmp_path / "env"))
    assert resolve_home(tmp_path / "arg") == (tmp_path / "arg").resolve()
    assert resolve_home() == (tmp_path / "env").resolve()
    monkeypatch.delenv("MADANG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    assert resolve_home() == (tmp_path / "user/.madang").resolve()


def test_init_uses_env_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MADANG_HOME", str(tmp_path / "env"))
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert (tmp_path / "env/profile.md").is_file()
    assert (tmp_path / "env/config.yaml").is_file()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_refuses_unrelated_folder(home: Path) -> None:
    home.mkdir()
    (home / "notes.txt").write_text("mine")
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 1
    assert "refusing" in result.output
    assert sorted(p.name for p in home.iterdir()) == ["notes.txt"]


def test_git_timeout_raises(tmp_path: Path) -> None:
    from madang import git

    with pytest.raises(git.GitError, match="timed out"):
        git.run(tmp_path, "version", timeout=1e-9)
