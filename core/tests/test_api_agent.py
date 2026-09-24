"""에이전트 경로: state.md 작업·결정·산출물, 코드 저장소 커밋·push, 승격."""

from pathlib import Path

import pytest
from api_support import git, page_dir, subjects

from madang.store import pages


def test_tasks_decisions_and_artifacts(
    client,
    home,
    page,
    contract,
) -> None:
    base = f"/pages/{page}/state"
    task = contract.check(
        client.patch(
            f"{base}/tasks",
            json={"id": "T1", "status": "doing", "title": "원인 분석"},
        ),
        200,
    )
    assert task == {"id": "T1", "title": "원인 분석", "status": "doing"}
    due = contract.check(
        client.patch(
            f"{base}/tasks",
            json={"id": "T1", "status": "done", "due": "2026-09-26"},
        ),
        200,
    )
    assert due["due"] == "2026-09-26"
    contract.check(
        client.patch(f"{base}/tasks", json={"id": "T2", "status": "todo"}), 400
    )
    contract.check(
        client.patch(f"{base}/tasks", json={"id": "T1", "status": "nope"}), 400
    )

    decision = contract.check(
        client.post(
            f"{base}/decisions",
            json={
                "id": "D1",
                "topic": "지원처별 차이",
                "choice": "overlay",
                "options": ["overlay", "copy"],
            },
        ),
        201,
    )
    assert decision["state"] == "confirmed" and decision["by"] == "human"
    contract.check(
        client.post(
            f"{base}/decisions",
            json={"id": "D1", "topic": "x", "choice": "a", "options": ["a"]},
        ),
        400,
    )

    folder = page_dir(home, page)
    (folder / "blocks/b01-notes.md").write_text("노트\n")
    artifacts = contract.check(
        client.post(f"{base}/artifacts", json={"path": "blocks/b01-notes.md"}),
        200,
    )
    assert artifacts == ["blocks/b01-notes.md"]
    missing = client.post(f"{base}/artifacts", json={"path": "blocks/nope.md"})
    body = contract.check(missing, 400)
    assert body["issues"][0]["code"] == "artifact-missing"
    state = pages.read_header(folder / "state.md")
    assert state["artifacts"] == ["blocks/b01-notes.md"]
    assert subjects(home)[0] == f"[{page}] edit state.md"
    assert git(home, "status", "--porcelain") == ""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "t")
    git(path, "config", "user.email", "t@example.com")
    (path / "README.md").write_text("repo\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return path


def test_repo_commit_push_and_promote(
    client,
    home,
    repo: Path,
    tmp_path: Path,
    contract,
) -> None:
    no_repo = client.post("/spaces/root/repo/commit", json={"message": "x"})
    assert contract.check(no_repo, 409)["error"] == "no_repo"
    contract.check(client.post("/spaces/nope/repo/push"), 404)

    contract.check(
        client.post(
            "/spaces", json={"slug": "code", "title": "코드", "repo": str(repo)}
        ),
        201,
    )
    (repo / "lock.ts").write_text("export {}\n")
    result = contract.check(
        client.post("/spaces/code/repo/commit", json={"message": "feat: lock"}),
        200,
    )
    assert result["commit"] == git(repo, "rev-parse", "--short", "HEAD").strip()
    contract.check(
        client.post("/spaces/code/repo/commit", json={"message": "again"}), 409
    )
    contract.check(client.post("/spaces/code/repo/push"), 409)

    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    pushed = contract.check(client.post("/spaces/code/repo/push"), 200)
    assert pushed == {"branch": "main", "remote": "origin"}

    page_id = client.post("/spaces/code/pages", json={"title": "문서"}).json()[
        "id"
    ]
    client.post(
        f"/pages/{page_id}/blocks",
        json={"type": "doc", "name": "design", "content": "설계\n"},
    )
    promoted = contract.check(
        client.post(f"/pages/{page_id}/blocks/b01/promote"), 200
    )
    assert promoted["path"] == "repo:docs/design.md" and promoted["commit"]
    again = contract.check(
        client.post(f"/pages/{page_id}/blocks/b01/promote"), 200
    )
    assert again["path"] == "repo:docs/design.md" and "commit" not in again
    contract.check(client.post(f"/pages/{page_id}/blocks/b09/promote"), 404)
    assert (repo / "docs/design.md").read_text().endswith("설계\n")
    assert git(home, "status", "--porcelain") == ""
