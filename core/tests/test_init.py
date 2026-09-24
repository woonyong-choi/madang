import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from madang import __version__
from madang.cli import app
from madang.config import MadangConfig, RoutesConfig, load_config, resolve_home

runner = CliRunner()


def git(home: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(home), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps user and system git config (signing, hooks, ...) out of tests."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def test_init_creates_home(home: Path) -> None:
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output

    for rel in (
        "config/madang.yaml",
        "config/routes.yaml",
        "config/runners.yaml",
        "root.md",
        "spaces/root/space.md",
        ".gitignore",
    ):
        assert (home / rel).is_file(), rel
    assert (home / "spaces/root/pages").is_dir()
    assert (home / "templates").is_dir()
    assert not (home / "config/secrets.yaml").exists()

    space = (home / "spaces/root/space.md").read_text()
    assert space.startswith("---\n")
    assert "slug: root" in space
    assert "title:" in space
    assert "repo: null" in space

    ignored = (home / ".gitignore").read_text().split()
    assert set(ignored) >= {"scratch/", "secrets.yaml", "core.db", "core.port"}

    log = git(home, "log", "--format=%s").splitlines()
    assert log == ["[home] init"]
    assert git(home, "status", "--porcelain") == ""


def test_init_is_idempotent(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    root_md = home / "root.md"
    root_md.write_text("my notes\n")

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "already initialized" in result.output
    assert root_md.read_text() == "my notes\n"
    assert len(git(home, "log", "--oneline").splitlines()) == 1


def test_init_restores_missing_file(home: Path) -> None:
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    git(home, "rm", "-q", "root.md")
    git(
        home,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "-m",
        "drop root",
    )

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert (home / "root.md").is_file()
    assert git(home, "log", "--format=%s").splitlines()[0] == "[home] init"
    assert git(home, "show", "--name-only", "--format=", "HEAD").split() == [
        "root.md"
    ]
    assert git(home, "status", "--porcelain") == ""


def test_init_recovers_from_failed_commit(home: Path) -> None:
    home.mkdir()
    git(home, "init", "-q")
    hook = home / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 1
    assert "error:" in result.output

    hook.unlink()
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert git(home, "log", "--format=%s").splitlines() == ["[home] init"]
    assert git(home, "status", "--porcelain") == ""


def test_init_rejects_file_home(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("x")
    result = runner.invoke(app, ["init", "--home", str(target)])
    assert result.exit_code == 1
    assert "error:" in result.output


def test_gitignore_is_applied(home: Path) -> None:
    runner.invoke(app, ["init", "--home", str(home)])
    (home / "core.db").write_text("x")
    (home / "core.port").write_text("7470")
    (home / "config/secrets.yaml").write_text("key: v")
    (home / "spaces/root/pages/p/scratch").mkdir(parents=True)
    (home / "spaces/root/pages/p/scratch/tmp").write_text("x")
    assert git(home, "status", "--porcelain") == ""


def test_load_config(home: Path) -> None:
    runner.invoke(app, ["init", "--home", str(home)])
    cfg = load_config(home)
    assert cfg.home == home.resolve()
    assert cfg.madang.core.port == 7470
    assert cfg.madang.core.bind == "127.0.0.1"
    assert cfg.madang.limits.state_tokens == 2000
    assert cfg.madang.limits.run_timeout_minutes["design"] == 30
    assert cfg.madang.home_remote is None
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


def test_init_refuses_repository_with_history(home: Path) -> None:
    home.mkdir()
    git(home, "init", "-q")
    git(
        home,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 1
    assert not (home / "config").exists()


def test_init_commits_unsigned(home: Path, tmp_path: Path) -> None:
    (tmp_path / "gitconfig").write_text(
        "[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n"
    )
    result = runner.invoke(app, ["init", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert git(home, "log", "--format=%s") == "[home] init\n"


def test_git_timeout_raises(tmp_path: Path) -> None:
    from madang.store import git as store_git

    with pytest.raises(store_git.GitError, match="timed out"):
        store_git.run(tmp_path, "version", timeout=1e-9)
