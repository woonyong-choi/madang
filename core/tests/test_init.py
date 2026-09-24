from pathlib import Path

import pytest
from typer.testing import CliRunner

from madang import __version__
from madang.cli import app
from madang.config import MadangConfig, RoutesConfig, load_config, resolve_home

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

    assert sorted(
        p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()
    ) == [
        "config/madang.yaml",
        "config/routes.yaml",
        "config/runners.yaml",
        "root.md",
    ]
    assert not (home / ".git").exists()
    settings = (home / "config/madang.yaml").read_text()
    assert "projects: []" in settings
    assert "commit_records: false" in settings


def test_init_is_idempotent(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    root_md = home / "root.md"
    root_md.write_text("my notes\n")

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "already initialized" in result.output
    assert root_md.read_text() == "my notes\n"


def test_init_restores_missing_file(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    (home / "root.md").unlink()

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "1 files" in result.output
    assert (home / "root.md").is_file()


def test_init_refuses_old_layout(home: Path) -> None:
    (home / "spaces/root/pages").mkdir(parents=True)
    (home / "config").mkdir()
    (home / "config/madang.yaml").write_text("home_remote: null\n")
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 1
    assert "old app home layout" in result.output
    assert not (home / "root.md").exists()
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
    assert cfg.madang.limits.state_tokens == 2000
    assert cfg.madang.limits.run_timeout_minutes["design"] == 30
    assert cfg.madang.projects == []
    assert cfg.madang.commit_records is False
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
    path = home / "config/madang.yaml"
    path.write_text(path.read_text().replace("port: 7470", "port: 7480"))
    assert load_config(home).madang.core.port == 7480


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
    assert (tmp_path / "env/root.md").is_file()


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
    from madang.store import git as store_git

    with pytest.raises(store_git.GitError, match="timed out"):
        store_git.run(tmp_path, "version", timeout=1e-9)
