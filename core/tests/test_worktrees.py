from pathlib import Path

import pytest

from madang import git, recorder
from madang.git import worktree
from madang.recorder.undo import read_log, track
from madang.store import pages, projects, worktrees
from madang.store.home import init_home
from madang.store.page import work_dir


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    init_home(path)
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    git.run(path, "init", "-q", "-b", "main")
    (path / "app.py").write_text("v = 1\n")
    git.stage(path)
    git.commit(path, "init")
    return path


def code_page(home: Path, root: Path, kind: str = "code") -> Path:
    project = projects.add(home, root, project_id="work")
    return pages.create_page(project.pages_dir, "lock", slug="lock", kind=kind)


def commit_in(path: Path, name: str, text: str) -> str:
    (path / name).write_text(text)
    git.stage(path)
    return git.commit(path, f"edit {name}")


def test_code_page_gets_worktree_outside_project(
    home: Path, repo: Path
) -> None:
    page = code_page(home, repo)

    path = worktrees.open_page(page)

    assert path == repo.parent / "work.wt" / page.name
    assert git.current_branch(path) == f"page/{page.name}"
    assert not (path / ".madang").exists()
    assert (repo / ".madang" / "pages" / page.name / "page.md").is_file()
    assert work_dir(page) == path
    assert worktrees.open_page(page) == path  # 다시 열어도 같은 것


def test_other_pages_and_folders_get_no_worktree(
    home: Path, repo: Path, tmp_path: Path
) -> None:
    doc = code_page(home, repo, kind="doc")
    assert worktrees.open_page(doc) is None
    assert work_dir(doc) == repo

    plain = tmp_path / "notes"
    plain.mkdir()
    project = projects.add(home, plain, project_id="notes")
    page = pages.create_page(project.pages_dir, "x", kind="code")
    assert worktrees.open_page(page) is None


def test_tracked_records_stay_out_of_worktree(home: Path, repo: Path) -> None:
    page = code_page(home, repo)
    config = repo / ".madang" / "config.yaml"
    config.write_text("track: true\n")
    git.run(repo, "add", "-f", ".madang/config.yaml")
    git.commit(repo, "track records")

    path = worktrees.open_page(page)

    assert path is not None
    assert not (path / ".madang").exists()
    assert (path / "app.py").is_file()


def test_merge_cleans_up_and_undo_reverts(home: Path, repo: Path) -> None:
    page = code_page(home, repo)
    path = worktrees.open_page(page)
    assert path is not None
    commit_in(path, "lock.py", "locked = True\n")
    n = recorder.begin(page)

    result = worktrees.merge_page(page)
    assert result.commit is not None
    recorder.record_git(page, n, "merge", repo, result.before, result.commit)
    track(page, n)  # 실행 기록을 다시 적어도 git 부작용은 남는다

    assert (repo / "lock.py").is_file()
    assert not path.exists()
    assert not (repo.parent / "work.wt").exists()
    assert not git.has_branch(repo, f"page/{page.name}")
    effect = read_log(page, n).effects[-1]
    assert (effect.kind, effect.before) == ("merge", result.before)

    undone = recorder.undo(page, n)

    assert not (repo / "lock.py").exists()
    assert undone.reverted == [git.rev_parse(repo)]
    assert git.log(repo)[0].subject.startswith("Revert")
    with pytest.raises(recorder.UndoError, match="already undone"):
        recorder.undo(page, n)


def test_undo_reverts_commits_newest_first(home: Path, repo: Path) -> None:
    page = code_page(home, repo)
    n = recorder.begin(page)
    for text in ("v = 2\n", "v = 3\n"):
        before = git.rev_parse(repo)
        sha = commit_in(repo, "app.py", text)
        recorder.record_git(page, n, "commit", repo, before, sha)

    recorder.undo(page, n)

    assert (repo / "app.py").read_text() == "v = 1\n"


def test_undo_refuses_commit_gone_from_history(home: Path, repo: Path) -> None:
    page = code_page(home, repo)
    n = recorder.begin(page)
    before = git.rev_parse(repo)
    sha = commit_in(repo, "app.py", "v = 2\n")
    recorder.record_git(page, n, "commit", repo, before, sha)
    git.run(repo, "reset", "-q", "--keep", before)

    with pytest.raises(recorder.UndoConflictError) as caught:
        recorder.undo(page, n)
    assert caught.value.paths == [f"{repo}@{sha[:12]}"]
    assert read_log(page, n).undone is None


def test_conflicting_merge_keeps_worktree(home: Path, repo: Path) -> None:
    page = code_page(home, repo)
    path = worktrees.open_page(page)
    assert path is not None
    commit_in(path, "app.py", "v = 'page'\n")
    commit_in(repo, "app.py", "v = 'main'\n")

    assert git.merge_conflicts(repo, worktrees.branch_for(page.name)) == [
        "app.py"
    ]
    result = worktrees.merge_page(page)

    assert result.commit is None
    assert result.conflicts == ["app.py"]
    assert path.is_dir()
    assert git.status(repo) == {}


def test_merge_refuses_uncommitted_worktree(home: Path, repo: Path) -> None:
    page = code_page(home, repo)
    path = worktrees.open_page(page)
    assert path is not None
    (path / "app.py").write_text("dirty\n")

    with pytest.raises(worktrees.PageWorktreeError, match="uncommitted"):
        worktrees.merge_page(page)
    assert [w.branch for w in worktree.list_worktrees(repo)] == [
        "main",
        f"page/{page.name}",
    ]
