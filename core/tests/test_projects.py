import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from madang.cli import app
from madang.store import pages, projects
from madang.store.home import init_home

runner = CliRunner()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    init_home(root)
    return root


def folder(tmp_path: Path, name: str, *, repo: bool = False) -> Path:
    path = tmp_path / name
    path.mkdir()
    if repo:
        git(path, "init", "-q", "-b", "main")
        (path / "README.md").write_text("x\n")
        git(path, "add", "-A")
        git(
            path,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "init",
        )
    return path


def test_add_creates_records_ignored_by_git(home: Path, tmp_path: Path) -> None:
    path = folder(tmp_path, "Madang Repo", repo=True)
    project = projects.add(home, path)

    assert project.id == "madang-repo"
    assert project.title == "Madang Repo"
    assert project.root == path.resolve()
    records = path / ".madang"
    assert (records / ".gitignore").read_text().splitlines()[-1] == "*"
    assert (records / "project.md").is_file()
    assert (records / "pages").is_dir()
    assert (records / "trash").is_dir()
    pages.create_page(project.pages_dir, "메모")
    assert git(path, "status", "--porcelain") == ""


def test_commit_records_keeps_pages_in_git(home: Path, tmp_path: Path) -> None:
    settings = home / "config/madang.yaml"
    settings.write_text(
        settings.read_text().replace(
            "commit_records: false", "commit_records: true"
        )
    )
    path = folder(tmp_path, "notes", repo=True)
    project = projects.add(home, path)
    page_dir = pages.create_page(project.pages_dir, "notes")
    (page_dir / "scratch").mkdir()
    (page_dir / "scratch" / "tmp.md").write_text("x\n")

    status = git(path, "status", "--porcelain", "--untracked-files=all")
    assert f".madang/pages/{page_dir.name}/page.md" in status
    assert "scratch" not in status


def test_add_keeps_existing_records(home: Path, tmp_path: Path) -> None:
    path = folder(tmp_path, "notes")
    (path / ".madang").mkdir()
    (path / ".madang" / "project.md").write_text("내 메모\n")
    projects.add(home, path)
    assert (path / ".madang" / "project.md").read_text() == "내 메모\n"


def test_add_refusals(home: Path, tmp_path: Path) -> None:
    path = folder(tmp_path, "notes")
    projects.add(home, path)
    with pytest.raises(FileExistsError, match="already registered"):
        projects.add(home, path)
    with pytest.raises(projects.ProjectError, match="not a folder"):
        projects.add(home, tmp_path / "missing")
    other = folder(tmp_path, "other")
    with pytest.raises(FileExistsError, match="already exists"):
        projects.add(home, other, project_id="notes")
    with pytest.raises(projects.ProjectError, match="invalid project id"):
        projects.add(home, other, project_id="Bad Id")
    with pytest.raises(FileNotFoundError, match="nope"):
        projects.add(home, other, settings={"parent": "nope"})


def test_ids_get_a_number_when_taken(home: Path, tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ids = [
        projects.add(home, folder(tmp_path / "a", "work")).id,
        projects.add(home, folder(tmp_path / "b", "work")).id,
    ]
    assert ids == ["work", "work-2"]


def test_update_and_remove(home: Path, tmp_path: Path) -> None:
    parent = projects.add(home, folder(tmp_path, "jobs"))
    child = projects.add(home, folder(tmp_path, "cv"))

    moved = projects.update(
        home, child.id, {"parent": parent.id, "icon": "doc", "title": "이력서"}
    )
    assert (moved.parent, moved.icon, moved.title) == ("jobs", "doc", "이력서")
    with pytest.raises(projects.ProjectError, match="cannot be the parent"):
        projects.update(home, parent.id, {"parent": child.id})
    with pytest.raises(projects.ProjectError, match="child projects: cv"):
        projects.remove(home, parent.id)

    assert projects.update(home, child.id, {"icon": None}).icon is None
    projects.remove(home, child.id)
    assert [p.id for p in projects.load(home)] == ["jobs"]
    assert (tmp_path / "cv" / ".madang" / "project.md").is_file()


def test_saving_keeps_other_settings_and_comments(
    home: Path, tmp_path: Path
) -> None:
    settings = home / "config/madang.yaml"
    before = settings.read_text()
    projects.add(home, folder(tmp_path, "notes"), title="노트")
    after = settings.read_text()
    assert after.startswith(before.split("projects:")[0])
    assert "title: 노트" in after
    projects.remove(home, "notes")
    assert settings.read_text() == before


def test_cli_project_add_list_and_page_new(home: Path, tmp_path: Path) -> None:
    path = folder(tmp_path, "notes")
    added = runner.invoke(
        app, ["project", "add", str(path), "--id", "n", "--home", str(home)]
    )
    assert added.exit_code == 0, added.output
    assert added.output.strip() == "n"
    listed = runner.invoke(app, ["project", "list", "--home", str(home)])
    assert listed.output.strip() == f"n\t{path.resolve()}"

    made = runner.invoke(
        app,
        [
            "page",
            "new",
            "--title",
            "첫 페이지",
            "--project",
            "n",
            "--slug",
            "first",
            "--home",
            str(home),
        ],
    )
    assert made.exit_code == 0, made.output
    page_id = made.output.strip()
    assert page_id.endswith("-first")
    assert (path / ".madang" / "pages" / page_id / "page.md").is_file()
    assert pages.find_page(home, page_id) == (
        path.resolve() / ".madang" / "pages" / page_id
    )

    missing = runner.invoke(
        app,
        ["page", "new", "--title", "x", "--project", "nope"],
        env={"MADANG_HOME": str(home)},
    )
    assert missing.exit_code == 1
    assert "project 'nope' not found" in missing.output
