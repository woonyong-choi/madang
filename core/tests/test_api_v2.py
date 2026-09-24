"""v2 경로: 설정, 사용량, 파일 트리, 뷰어, 게시, 되돌리기, 묻는 블록."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from api_support import PROJECT, git, page_dir, set_status

from madang.store import frontmatter, pages, runs

REPO = Path(__file__).resolve().parents[2]
VIEWER = REPO / "templates/viewers/resume-basic"
WAIT = 20.0


@pytest.fixture
def events(client, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """core가 낸 이벤트를 모은다."""
    seen: list[dict] = []
    monkeypatch.setattr(client.app.state.core.hub, "publish", seen.append)
    return seen


def of_type(events: list[dict], kind: str) -> list[dict]:
    return [e for e in events if e["type"] == kind]


def join(client, page_id: str) -> None:
    client.app.state.core.flows.join(page_id, WAIT)
    assert not client.app.state.core.flows.busy(page_id)


# 설정


def test_app_config_is_checked_before_saving(client, home, contract) -> None:
    text = contract.check(client.get("/config"), 200)["text"]
    assert "routes:" in text

    broken = text.replace("  port: 7470", "  port: nope")
    body = contract.check(client.put("/config", json={"text": broken}), 400)
    issue = body["issues"][0]
    assert issue["path"] == "config.yaml" and issue["line"] is not None
    assert "core.port" in issue["message"]
    assert (home / "config.yaml").read_text() == text

    bad_yaml = contract.check(client.put("/config", json={"text": "a: ["}), 400)
    assert bad_yaml["issues"][0]["code"] == "invalid-yaml"

    changed = text.replace("language: ko", "language: en")
    contract.check(client.put("/config", json={"text": changed}), 200)
    assert "language: en" in (home / "config.yaml").read_text()


def test_project_config_is_checked_before_saving(
    client, project_root, events, contract
) -> None:
    url = f"/projects/{PROJECT}/config"
    assert contract.check(client.get(url), 200) == {"text": ""}
    body = contract.check(
        client.put(url, json={"text": "track: false\nrunz: []\n"}), 400
    )
    assert body["issues"][0]["line"] == 2
    assert "runz" in body["issues"][0]["message"]

    text = "policy:\n  deny: [push]\n"
    contract.check(client.put(url, json={"text": text}), 200)
    assert (project_root / ".madang/config.yaml").read_text() == text
    assert contract.check(client.get(url), 200) == {"text": text}
    updated = of_type(events, "project.updated")
    assert updated and updated[0]["project"] == PROJECT
    contract.check(client.get("/projects/nope/config"), 404)


# 사용량


def usage_line(**fields) -> str:
    record = {
        "type": "assistant",
        "sessionId": "s1",
        "requestId": "r1",
        "timestamp": "2026-09-24T01:00:00Z",
        "message": {
            "id": "m1",
            "model": "claude-opus-5-5",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 7,
            },
        },
    }
    record.update(fields)
    return json.dumps(record)


def test_usage_counts_each_response_once(
    client, tmp_path: Path, contract
) -> None:
    claude = tmp_path / "claude"
    core = client.app.state.core
    core.claude_dir = claude
    empty = contract.check(client.get("/usage"), 200)
    assert empty["tools"][0]["available"] is False
    assert empty["tools"][0]["messages"] == 0

    folder = claude / "projects" / "-work"
    folder.mkdir(parents=True)
    today = datetime.now(UTC).isoformat()
    lines = [
        usage_line(timestamp=today),
        usage_line(timestamp=today),  # 같은 응답의 되풀이
        usage_line(
            timestamp=today,
            requestId="r2",
            sessionId="s2",
            message={
                "id": "m2",
                "model": "claude-sonnet-5",
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        ),
        json.dumps({"type": "user", "message": {"content": "hi"}}),
        "not json",
    ]
    (folder / "s1.jsonl").write_text("\n".join(lines) + "\n")

    body = contract.check(client.get("/usage", params={"days": 1}), 200)
    tool = body["tools"][0]
    assert tool["available"] is True
    assert (tool["messages"], tool["sessions"]) == (2, 2)
    assert tool["input_tokens"] == 11 and tool["cache_read_tokens"] == 100
    assert [m["model"] for m in tool["models"]] == [
        "claude-opus-5-5",
        "claude-sonnet-5",
    ]
    contract.check(client.get("/usage", params={"days": 0}), 400)


# 파일 트리


def test_file_tree_lenses(client, home, project_root, page, contract) -> None:
    (project_root / "site").mkdir()
    (project_root / "site" / "index.html").write_text("<h1>hi</h1>\n")
    (project_root / "notes.md").write_text("노트\n")
    config = project_root / ".madang/config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "runs": [
                    {"name": "site", "cwd": "site", "command": "serve"},
                    {"name": "all", "command": "make"},
                ]
            }
        )
    )
    url = f"/projects/{PROJECT}/files"
    tree = contract.check(client.get(url), 200)
    paths = [e["path"] for e in tree["entries"]]
    assert paths[0] == ".madang"
    assert paths.index(".madang/config.yaml") < paths.index("notes.md")
    site = next(e for e in tree["entries"] if e["path"] == "site")
    assert site == {"path": "site", "type": "dir", "runs": ["site"]}
    assert tree["runs"] == ["all"] and tree["truncated"] is False

    folder = page_dir(home, page)
    (folder / "blocks" / "b01-a.md").write_text("a\n")
    header, body = frontmatter.read(folder / "ledger.md")
    header["artifacts"] = ["blocks/b01-a.md"]
    header["reads"] = ["repo:notes.md", "repo:gone.md"]
    (folder / "ledger.md").write_text(frontmatter.dumps(header, body))
    mine = contract.check(
        client.get(url, params={"lens": "page", "page": page}), 200
    )
    files = [e["path"] for e in mine["entries"] if e["type"] == "file"]
    assert files == [f".madang/pages/{page}/blocks/b01-a.md", "notes.md"]
    contract.check(client.get(url, params={"lens": "page"}), 400)

    no_repo = contract.check(client.get(url, params={"lens": "changed"}), 409)
    assert no_repo["error"] == "no_repo"
    git(project_root, "init", "-q")
    changed = contract.check(client.get(url, params={"lens": "changed"}), 200)
    notes = next(e for e in changed["entries"] if e["path"] == "notes.md")
    assert notes["change"] == "??"


# 뷰어


def test_viewers_register_list_and_break(
    client, tmp_path: Path, events, contract
) -> None:
    source = tmp_path / "viewers" / "resume"
    shutil.copytree(VIEWER, source)
    made = contract.check(
        client.post("/viewers", json={"source": str(source)}), 201
    )
    assert made["name"] == "resume/basic" and made["status"] == "ok"
    assert made["scope"] == "registry" and made["version"] == "1.0.0"
    assert of_type(events, "viewer.changed")[0]["data"] == {
        "name": "resume/basic",
        "status": "ok",
    }
    again = client.post("/viewers", json={"source": str(source)})
    assert contract.check(again, 409)["error"] == "conflict"
    contract.check(
        client.post("/viewers", json={"source": str(tmp_path / "none")}), 400
    )

    shutil.rmtree(source)
    listed = contract.check(client.get("/viewers"), 200)
    assert [(v["name"], v["status"]) for v in listed] == [
        ("resume/basic", "broken")
    ]


def test_project_viewers_come_first(client, project_root, contract) -> None:
    shutil.copytree(VIEWER, project_root / ".madang/viewers/resume")
    listed = contract.check(
        client.get("/viewers", params={"project": PROJECT}), 200
    )
    assert listed[0]["scope"] == "project"
    assert listed[0]["project"] == PROJECT
    contract.check(client.get("/viewers", params={"project": "nope"}), 404)


# 게시


def test_publish_status_publish_and_undo(
    client, project_root, events, contract
) -> None:
    url = f"/projects/{PROJECT}/publish"
    missing = contract.check(client.post(url), 409)
    assert missing["error"] == "target-missing"

    (project_root / "docs").mkdir()
    (project_root / "docs" / "guide.md").write_text("# 안내\n")
    (project_root / ".madang/config.yaml").write_text(
        "publish:\n  include: [docs]\n  target: folder:site\n"
    )
    status = contract.check(client.get(url), 200)
    assert status == {
        "target": "folder:site",
        "include": ["docs"],
        "auto_publish": False,
    }
    done = contract.check(client.post(url), 200)
    assert done["changed"] is True and done["documents"] == 1
    assert (project_root / "site" / "docs" / "guide.html").is_file()
    assert contract.check(client.post(url), 200)["changed"] is False
    latest = contract.check(client.get(url), 200)["latest"]
    assert latest["n"] == done["record"]["n"]

    undone = contract.check(client.post(f"{url}/undo"), 200)
    assert undone["record"]["undone"]
    assert not (project_root / "site" / "docs" / "guide.html").exists()
    again = contract.check(client.post(f"{url}/undo"), 409)
    assert again["error"] == "nothing-to-undo"
    published = of_type(events, "publish.done")
    assert [e["data"]["undo"] for e in published] == [False, True]
    for event in events:
        contract.event(event)


# 되돌리기


def test_undo_run_restores_page_files(
    client, home, page, script, contract
) -> None:
    script.acts += [set_status("review"), set_status("review")]
    contract.check(
        client.post(f"/pages/{page}/messages", json={"text": "구현해줘"}), 202
    )
    join(client, page)
    folder = page_dir(home, page)
    last = runs.list_runs(folder)[-1]
    assert pages.read_header(folder / "ledger.md")["status"] == "done"

    result = contract.check(client.post(f"/pages/{page}/runs/{last}/undo"), 200)
    assert result["run"] == last and "ledger.md" in result["restored"]
    assert pages.read_header(folder / "ledger.md")["status"] == "review"
    again = contract.check(client.post(f"/pages/{page}/runs/{last}/undo"), 409)
    assert "already undone" in again["message"]
    contract.check(client.post(f"/pages/{page}/runs/99/undo"), 404)


# 묻는 블록


@pytest.fixture
def code_page(client, tmp_path: Path) -> str:
    """테스트 명령 없이 테스트를 요구하는 git 프로젝트의 코드 페이지."""
    root = tmp_path / "code"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text("v = 1\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "i")
    assert client.post("/projects", json={"path": str(root), "id": "code"})
    created = client.post("/projects/code/pages", json={"title": "잠금"})
    page_id = created.json()["id"]
    page_md = root / ".madang/pages" / page_id / "page.md"
    header, body = frontmatter.read(page_md)
    header["kind"] = "code"
    page_md.write_text(frontmatter.dumps(header, body))
    return page_id


def test_policy_refusal_asks_and_answer_goes_through_the_block(
    client, code_page, script, events, contract
) -> None:
    script.acts += [set_status("review"), set_status("review")]
    contract.check(
        client.post(
            f"/pages/{code_page}/messages", json={"text": "잠금 구현해줘"}
        ),
        202,
    )
    join(client, code_page)
    asked = of_type(events, "ask.created")
    assert len(asked) == 1
    block = asked[0]["block"]
    assert asked[0]["data"]["reasons"] == ["테스트 명령 없음"]
    assert "merge" in asked[0]["data"]["options"]
    waiting = contract.check(client.get(f"/pages/{code_page}"), 200)["waiting"]
    assert waiting["decision"]["ask"] == block

    url = f"/pages/{code_page}/asks/{block}/answer"
    contract.check(client.post(url, json={"choice": "nope"}), 400)
    contract.check(
        client.post(
            f"/pages/{code_page}/asks/b99/answer", json={"choice": "stop"}
        ),
        404,
    )
    contract.check(client.post(url, json={"choice": "stop"}), 202)
    join(client, code_page)
    assert "waiting" not in client.get(f"/pages/{code_page}").json()
    for event in events:
        contract.event(event)
