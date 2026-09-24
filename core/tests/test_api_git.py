"""git 탭 경로와 에이전트 커밋: 정책을 지나 core git 모듈로만 바꾼다."""

from pathlib import Path

import pytest
from api_support import PROJECT, git, page_dir

from madang.store import frontmatter, worktrees

BASE = f"/projects/{PROJECT}/git"


@pytest.fixture
def events(client, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []
    monkeypatch.setattr(client.app.state.core.hub, "publish", seen.append)
    return seen


def test_init_then_stage_commit_log_and_branches(
    client, project_root: Path, events, contract
) -> None:
    before = contract.check(client.get(f"{BASE}/status"), 200)
    assert before == {
        "repository": False,
        "folder": str(project_root),
        "files": [],
    }
    assert contract.check(client.get(f"{BASE}/diff"), 409)["error"] == "no_repo"

    contract.check(client.post(f"{BASE}/init"), 201)
    contract.check(client.post(f"{BASE}/init"), 409)
    git(project_root, "config", "user.name", "t")
    git(project_root, "config", "user.email", "t@example.com")
    (project_root / "a.txt").write_text("a\n")
    status = contract.check(client.get(f"{BASE}/status"), 200)
    assert status["files"] == [{"path": "a.txt", "code": "??"}]  # .madang/ 빠짐

    staged = contract.check(client.post(f"{BASE}/stage", json={}), 200)
    assert staged["files"] == [{"path": "a.txt", "code": "A "}]
    diff = contract.check(
        client.get(f"{BASE}/diff", params={"staged": True}), 200
    )
    assert "+a" in diff["text"]
    empty = client.post(f"{BASE}/commit", json={"message": " "})
    contract.check(empty, 400)
    made = contract.check(
        client.post(f"{BASE}/commit", json={"message": "feat: add a"}), 200
    )
    assert made["commit"] == git(project_root, "rev-parse", "HEAD").strip()
    nothing = client.post(f"{BASE}/commit", json={"message": "again"})
    assert "nothing is staged" in contract.check(nothing, 409)["message"]

    log = contract.check(client.get(f"{BASE}/log"), 200)
    assert [c["subject"] for c in log] == ["feat: add a"]
    contract.check(client.get(f"{BASE}/log", params={"ref": "nope"}), 404)
    branches = contract.check(client.get(f"{BASE}/branches"), 200)
    assert branches["branches"] == [branches["current"]]
    trees = contract.check(client.get(f"{BASE}/worktrees"), 200)
    assert [(t["main"], t.get("page")) for t in trees] == [(True, None)]

    actions = [
        e["data"]["action"] for e in events if e["type"] == "git.changed"
    ]
    assert actions == ["init", "stage", "commit"]
    for event in events:
        contract.event(event)


def test_secrets_are_not_committed(
    client, project_root: Path, contract
) -> None:
    git(project_root, "init", "-q")
    (project_root / ".env").write_text("TOKEN=x\n")
    git(project_root, "add", ".env")
    refused = client.post(f"{BASE}/commit", json={"message": "leak"})
    assert ".env" in contract.check(refused, 409)["message"]


def test_push_and_pull_follow_policy(
    client, project_root: Path, tmp_path: Path, contract
) -> None:
    git(project_root, "init", "-q", "-b", "main")
    git(project_root, "config", "user.name", "t")
    git(project_root, "config", "user.email", "t@example.com")
    (project_root / "a.txt").write_text("a\n")
    git(project_root, "add", "a.txt")
    git(project_root, "commit", "-qm", "init")
    contract.check(client.post(f"{BASE}/push"), 409)  # 원격 없음

    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(project_root, "remote", "add", "origin", str(remote))
    pushed = contract.check(client.post(f"{BASE}/push"), 200)
    assert pushed == {"branch": "main", "remote": "origin"}
    git(project_root, "branch", "-u", "origin/main")
    pulled = contract.check(client.post(f"{BASE}/pull"), 200)
    assert pulled["branch"] == "main"

    (project_root / ".madang/config.yaml").write_text(
        "policy:\n  deny: [push]\n"
    )
    denied = contract.check(client.post(f"{BASE}/push"), 409)
    assert denied["error"] == "denied" and "push" in denied["message"]


# 코드 페이지 워크트리


@pytest.fixture
def repo(client, tmp_path: Path) -> Path:
    root = tmp_path / "code"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.com")
    (root / "README.md").write_text("code\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    assert client.post("/projects", json={"path": str(root), "id": "code"})
    return root


def code_page(client, home: Path) -> Path:
    page_id = client.post("/projects/code/pages", json={"title": "잠금"})
    folder = page_dir(home, page_id.json()["id"])
    header, body = frontmatter.read(folder / "page.md")
    header["kind"] = "code"
    (folder / "page.md").write_text(frontmatter.dumps(header, body))
    worktrees.open_page(folder)
    return folder


def test_agent_commit_goes_to_the_page_worktree(
    client, home: Path, repo: Path, contract
) -> None:
    folder = code_page(client, home)
    tree = repo.parent / "code.wt" / folder.name
    (tree / "lock.ts").write_text("export {}\n")
    main_head = git(repo, "rev-parse", "HEAD").strip()

    made = contract.check(
        client.post(
            "/projects/code/repo/commit",
            json={"message": "feat: lock", "page": folder.name},
        ),
        200,
    )
    branch = f"page/{folder.name}"
    assert made["commit"] == git(repo, "rev-parse", "--short", branch).strip()
    assert git(repo, "rev-parse", "HEAD").strip() == main_head
    assert git(repo, "status", "--porcelain") == ""
    shown = git(repo, "show", "--name-only", "--format=", branch).split()
    assert shown == ["lock.ts"]

    status = contract.check(
        client.get("/projects/code/git/status", params={"page": folder.name}),
        200,
    )
    assert status["folder"] == str(tree) and status["branch"] == branch
    trees = contract.check(client.get("/projects/code/git/worktrees"), 200)
    assert {t.get("page") for t in trees} == {None, folder.name}

    wrong = client.post(
        f"/projects/{PROJECT}/repo/commit",
        json={"message": "x", "page": folder.name},
    )
    contract.check(wrong, 400)


def test_agent_push_is_checked_by_policy(
    client, home: Path, repo: Path, contract
) -> None:
    folder = code_page(client, home)
    (repo / ".madang/config.yaml").write_text("policy:\n  deny: [push]\n")
    denied = client.post("/projects/code/repo/push", json={"page": folder.name})
    assert contract.check(denied, 409)["error"] == "denied"
