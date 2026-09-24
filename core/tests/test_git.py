import re
from pathlib import Path

import pytest

from madang import git
from madang.git import worktree

MADANG_SRC = Path(__file__).parent.parent / "madang"


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git.run(path, "init", "-q", "-b", "main")
    write(path, "a.txt", "a\n")
    git.stage(path)
    git.commit(path, "init")
    return path


def write(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")


def commit_file(repo: Path, name: str, text: str, message: str) -> str:
    write(repo, name, text)
    git.stage(repo, [name])
    return git.commit(repo, message)


def test_only_git_module_runs_git() -> None:
    call = re.compile(r"""\[\s*["']git["']""")
    found = [
        path.relative_to(MADANG_SRC).as_posix()
        for path in MADANG_SRC.rglob("*.py")
        if call.search(path.read_text(encoding="utf-8"))
    ]
    assert found == ["git/command.py"]


def test_status_stage_commit_log_diff(repo: Path) -> None:
    write(repo, "a.txt", "b\n")
    write(repo, "new.txt", "n\n")
    assert git.status(repo) == {"a.txt": " M", "new.txt": "??"}
    assert "+b" in git.diff(repo)

    git.stage(repo)
    assert git.has_staged_changes(repo)
    assert "+n" in git.diff(repo, staged=True)
    sha = git.commit(repo, "second")

    assert git.status(repo) == {}
    assert git.rev_parse(repo) == sha
    assert git.head(repo) == sha[: len(git.head(repo))]
    history = git.log(repo)
    assert [c.subject for c in history] == ["second", "init"]
    assert history[0].author == "madang"  # 작성자 설정이 없으면 대체 이름
    assert "a.txt" in git.diff(repo, history[1].hash, history[0].hash)


def test_branch_create_and_delete(repo: Path) -> None:
    assert git.current_branch(repo) == "main"
    git.create_branch(repo, "topic")
    assert git.branches(repo) == ["main", "topic"]
    assert git.has_branch(repo, "topic")
    git.delete_branch(repo, "topic")
    assert not git.has_branch(repo, "topic")


def test_merge_records_before_and_detects_conflicts(repo: Path) -> None:
    git.create_branch(repo, "clean")
    git.create_branch(repo, "clash")
    git.run(repo, "switch", "-q", "clean")
    commit_file(repo, "b.txt", "b\n", "add b")
    git.run(repo, "switch", "-q", "clash")
    commit_file(repo, "a.txt", "theirs\n", "edit a")
    git.run(repo, "switch", "-q", "main")
    commit_file(repo, "a.txt", "ours\n", "edit a on main")
    before = git.rev_parse(repo)

    assert git.merge_conflicts(repo, "clean") == []
    assert git.merge_conflicts(repo, "clash") == ["a.txt"]

    merged = git.merge(repo, "clean")
    assert merged.before == before
    assert merged.commit == git.rev_parse(repo)
    assert merged.conflicts == []

    stuck = git.merge(repo, "clash")
    assert stuck.commit is None
    assert stuck.conflicts == ["a.txt"]
    assert git.status(repo) == {}  # 충돌한 머지는 취소된다
    assert git.rev_parse(repo) == merged.commit


def test_revert_undoes_merge_with_new_commit(repo: Path) -> None:
    git.create_branch(repo, "topic")
    git.run(repo, "switch", "-q", "topic")
    commit_file(repo, "b.txt", "b\n", "add b")
    git.run(repo, "switch", "-q", "main")
    merged = git.merge(repo, "topic")
    assert merged.commit is not None

    undone = git.revert(repo, merged.commit, merge_parent=1)

    assert not (repo / "b.txt").exists()
    assert git.is_ancestor(repo, merged.commit, undone)


def test_push_and_pull_through_bare_remote(repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    git.run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    git.run(repo, "remote", "add", "origin", str(remote))
    git.push(repo, "origin", "main")
    clone = tmp_path / "clone"
    git.run(tmp_path, "clone", "-q", str(remote), str(clone))

    sha = commit_file(repo, "c.txt", "c\n", "add c")
    git.push(repo, "origin", "main")
    git.pull(clone)

    assert git.remotes(repo) == ["origin"]
    assert git.rev_parse(clone) == sha


def test_worktree_add_list_leave_out_and_remove(
    repo: Path, tmp_path: Path
) -> None:
    (repo / ".madang").mkdir()
    write(repo, ".madang/brief.md", "b\n")
    git.stage(repo)
    git.commit(repo, "track records")
    path = tmp_path / "repo.wt" / "p1"

    worktree.add(repo, path, "page/p1")
    worktree.leave_out(path, ".madang")

    listed = worktree.list_worktrees(repo)
    assert [w.branch for w in listed] == ["main", "page/p1"]
    assert listed[1].path.resolve() == path.resolve()
    assert not (path / ".madang").exists()
    assert (repo / ".madang" / "brief.md").is_file()  # 메인은 그대로
    assert git.status(path) == {}

    worktree.remove(repo, path)
    assert not path.exists()
    assert [w.branch for w in worktree.list_worktrees(repo)] == ["main"]


def test_remove_keeps_worktree_with_changes(repo: Path, tmp_path: Path) -> None:
    path = tmp_path / "repo.wt" / "p1"
    worktree.add(repo, path, "page/p1")
    write(path, "a.txt", "dirty\n")

    with pytest.raises(git.GitError):
        worktree.remove(repo, path)
    assert path.is_dir()
