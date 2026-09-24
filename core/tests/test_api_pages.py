"""프로젝트·페이지·블록·메모리·휴지통·템플릿 경로."""

import json

from api_support import PROJECT, page_dir

from madang.store import frontmatter, pages, runs

PAGES = f"/projects/{PROJECT}/pages"


# 프로젝트


def test_project_lifecycle(client, home, tmp_path, contract) -> None:
    (tmp_path / "jobs").mkdir()
    (tmp_path / "cv").mkdir()
    created = contract.check(
        client.post(
            "/projects",
            json={
                "path": str(tmp_path / "jobs"),
                "title": "지원",
                "color": "#3a5bd9",
            },
        ),
        201,
    )
    assert created["id"] == "jobs" and created["title"] == "지원"
    assert created["path"] == str((tmp_path / "jobs").resolve())
    assert created["color"] == "#3a5bd9" and created["pages"] == 0
    assert (tmp_path / "jobs/.madang/brief.md").is_file()
    contract.check(
        client.post("/projects", json={"path": str(tmp_path / "jobs")}), 409
    )
    contract.check(
        client.post("/projects", json={"path": str(tmp_path / "nope")}), 400
    )
    (tmp_path / "bad/.madang").mkdir(parents=True)
    (tmp_path / "bad/.madang/config.yaml").write_text("track: maybe\n")
    bad = client.post("/projects", json={"path": str(tmp_path / "bad")})
    assert "track" in contract.check(bad, 400)["message"]
    contract.check(
        client.post(
            "/projects", json={"path": str(tmp_path / "cv"), "id": "Bad Id"}
        ),
        400,
    )
    contract.check(
        client.post(
            "/projects",
            json={"path": str(tmp_path / "cv"), "parent": "nope"},
        ),
        404,
    )
    contract.check(
        client.post(
            "/projects",
            json={"path": str(tmp_path / "cv"), "id": "sub", "parent": "jobs"},
        ),
        201,
    )

    updated = contract.check(
        client.patch(
            "/projects/jobs", json={"title": "지원 2026", "sort": "title"}
        ),
        200,
    )
    assert updated["title"] == "지원 2026" and updated["sort"] == "title"
    contract.check(client.patch("/projects/jobs", json={"parent": "sub"}), 400)
    cleared = contract.check(
        client.patch("/projects/jobs", json={"color": None}), 200
    )
    assert "color" not in cleared
    contract.check(client.patch("/projects/nope", json={"title": "x"}), 404)
    contract.check(client.patch("/projects/jobs", json={"path": "/x"}), 400)

    listed = contract.check(client.get("/projects"), 200)
    assert [p["id"] for p in listed] == [PROJECT, "jobs", "sub"]

    contract.check(client.delete("/projects/jobs"), 409)  # 하위 프로젝트
    contract.check(client.delete("/projects/sub"), 204)
    contract.check(client.delete("/projects/sub"), 404)
    assert (tmp_path / "cv/.madang/brief.md").is_file()
    contract.check(client.delete("/projects/jobs"), 204)


# 페이지


def test_create_and_list_pages(client, home, project_root, contract) -> None:
    detail = contract.check(
        client.post(PAGES, json={"title": "이력서", "kind": "design"}),
        201,
    )
    assert detail["kind"] == "design" and detail["blocks"] == []
    assert detail["project"] == PROJECT
    folder = project_root / ".madang/pages" / detail["id"]
    assert (folder / "page.md").is_file()
    contract.check(client.post(PAGES, json={"title": "이력서"}), 409)
    contract.check(
        client.post(PAGES, json={"title": "x", "kind": "z"}),
        400,
    )
    contract.check(
        client.post("/projects/nope/pages", json={"title": "x"}), 404
    )
    second = client.post(PAGES, json={"title": "공고 분석"})
    pinned = second.json()["id"]
    contract.check(client.patch(f"/pages/{pinned}", json={"pinned": True}), 200)

    cards = contract.check(client.get(PAGES), 200)
    assert [c["id"] for c in cards] == [pinned, detail["id"]]
    assert cards[1]["status"] == "planning"
    assert cards[1]["project"] == PROJECT
    assert "last_run" not in cards[1]
    contract.check(client.get("/projects/nope/pages"), 404)
    assert not (home / "spaces").exists()


def test_page_card_preview_counts_and_last_run(
    client,
    home,
    page,
    contract,
) -> None:
    folder = page_dir(home, page)
    client.post(
        f"/pages/{page}/blocks",
        json={"type": "data", "name": "base", "content": "{}"},
    )
    client.post(
        f"/pages/{page}/blocks",
        json={
            "type": "view",
            "name": "resume",
            "template": "resume",
            "bindings": {"base": "b01"},
        },
    )
    from madang.store.log import append_message

    append_message(folder, "user", "첫 줄\n둘째 줄", {"target": "page"})
    record = runs.RunRecord(n=1, runner="codex", model="gpt-6-luna")
    record.result_status = "doing"
    runs.allocate(folder)
    runs.write_run(folder, record)

    card = contract.check(client.get(PAGES), 200)[0]
    assert card["preview"] == "첫 줄"
    assert card["block_counts"] == {
        "data": 1,
        "view": 1,
        "message": 1,
        "run": 1,
    }
    assert card["first_view"] == "b02"
    assert card["last_run"] == {
        "n": 1,
        "runner": "codex",
        "model": "gpt-6-luna",
        "result_status": "doing",
    }
    detail = contract.check(client.get(f"/pages/{page}"), 200)
    assert [b["type"] for b in detail["blocks"]] == ["data", "view", "message"]
    assert detail["blocks"][2]["target"] == {}
    assert detail["runs"][0]["n"] == 1 and "input" not in detail["runs"][0]


def test_update_page_order_tags_and_move(
    client,
    home,
    project_root,
    page,
    tmp_path,
    contract,
) -> None:
    for name in ("a", "b"):
        client.post(
            f"/pages/{page}/blocks",
            json={"type": "doc", "name": name, "content": "본문\n"},
        )
    card = contract.check(
        client.patch(
            f"/pages/{page}",
            json={"tags": ["지원"], "blocks_order": ["b02", "b01"]},
        ),
        200,
    )
    assert card["tags"] == ["지원"]
    order = pages.read_header(page_dir(home, page) / "page.md")["blocks"]
    assert order == ["b02", "b01"]
    contract.check(
        client.patch(f"/pages/{page}", json={"blocks_order": ["b01"]}), 400
    )
    contract.check(
        client.patch(f"/pages/{page}", json={"project": "nope"}), 404
    )

    (tmp_path / "jobs").mkdir()
    client.post("/projects", json={"path": str(tmp_path / "jobs")})
    moved = contract.check(
        client.patch(f"/pages/{page}", json={"project": "jobs"}), 200
    )
    assert moved["project"] == "jobs"
    assert (tmp_path / "jobs/.madang/pages" / page / "page.md").is_file()
    assert not (project_root / ".madang/pages" / page).exists()
    assert (
        contract.check(client.get(f"/pages/{page}"), 200)["project"] == "jobs"
    )


def test_delete_page_and_restore_from_trash(
    client,
    home,
    project_root,
    page,
    contract,
) -> None:
    contract.check(client.delete(f"/pages/{page}"), 204)
    contract.check(client.get(f"/pages/{page}"), 404)
    contract.check(client.delete(f"/pages/{page}"), 404)
    assert not (project_root / ".madang/pages" / page).exists()

    trash = contract.check(client.get("/trash"), 200)
    assert len(trash) == 1
    entry = trash[0]
    assert entry["page"] == page and entry.get("block") is None
    assert entry["project"] == PROJECT
    assert entry["paths"] == [f".madang/pages/{page}"]
    kept = project_root / ".madang/trash" / entry["id"]
    assert (kept / "files/pages" / page / "page.md").is_file()

    contract.check(client.post("/trash/zzzz/restore"), 404)
    restored = contract.check(client.post(f"/trash/{entry['id']}/restore"), 200)
    assert restored == {"id": entry["id"], "paths": entry["paths"]}
    contract.check(client.get(f"/pages/{page}"), 200)
    assert contract.check(client.get("/trash"), 200) == []
    assert not kept.exists()


def test_restore_refuses_taken_path(client, home, page, contract) -> None:
    client.delete(f"/pages/{page}")
    entry = client.get("/trash").json()[0]
    again = client.post(PAGES, json={"title": "이력서"}).json()["id"]
    assert again == page
    refused = contract.check(client.post(f"/trash/{entry['id']}/restore"), 409)
    assert "already exists" in refused["message"]


# 블록


def test_block_lifecycle(client, home, page, contract) -> None:
    folder = page_dir(home, page)
    header = contract.check(
        client.post(
            f"/pages/{page}/blocks",
            json={"type": "data", "name": "base", "content": '{"a": 1}'},
        ),
        201,
    )
    assert header == {
        "id": "b01",
        "type": "data",
        "file": "blocks/b01-base.json",
        "title": "base",
        "created_by": "user",
        "format": "json",
    }
    contract.check(
        client.post(
            f"/pages/{page}/blocks",
            json={"type": "data", "name": "bad", "content": "{"},
        ),
        400,
    )
    contract.check(
        client.post(
            f"/pages/{page}/blocks",
            json={"type": "view", "name": "cv", "template": "nope"},
        ),
        400,
    )
    view = contract.check(
        client.post(
            f"/pages/{page}/blocks",
            json={
                "type": "view",
                "name": "cv",
                "template": "resume@1",
                "bindings": {"base": "b01"},
            },
        ),
        201,
    )
    assert view["template"] == "resume@1"
    assert view["bindings"] == {"base": "b01"}

    block = contract.check(client.get(f"/pages/{page}/blocks/b01"), 200)
    assert block["content"] == '{"a": 1}'
    contract.check(client.get(f"/pages/{page}/blocks/b99"), 404)

    saved = contract.check(
        client.put(f"/pages/{page}/blocks/b01", json={"content": '{"a": 2}'}),
        200,
    )
    assert saved["content"] == '{"a": 2}'
    contract.check(
        client.put(f"/pages/{page}/blocks/b01", json={"content": "{"}), 400
    )

    patched = contract.check(
        client.patch(
            f"/pages/{page}/blocks/{view['id']}",
            json={
                "presets": {"기본": {"base": "b01"}},
                "active_preset": "기본",
                "theme": {"color.accent": "#b8322a"},
            },
        ),
        200,
    )
    assert patched["active_preset"] == "기본"
    view_file = folder / view["file"]
    stored, _ = frontmatter.read(view_file)
    assert stored["theme"] == {"color.accent": "#b8322a"}
    contract.check(
        client.patch(
            f"/pages/{page}/blocks/{view['id']}",
            json={"active_preset": "없음"},
        ),
        400,
    )
    contract.check(
        client.patch(
            f"/pages/{page}/blocks/b01", json={"title": "기본 데이터"}
        ),
        200,
    )
    meta = (folder / "blocks/b01-base.meta.yaml").read_text()
    assert "기본 데이터" in meta

    contract.check(client.delete(f"/pages/{page}/blocks/b01"), 204)
    contract.check(client.delete(f"/pages/{page}/blocks/b01"), 404)
    assert not (folder / "blocks/b01-base.json").exists()
    assert pages.read_header(folder / "page.md")["blocks"] == [view["id"]]

    entry = contract.check(client.get("/trash"), 200)[0]
    assert entry["block"] == "b01" and len(entry["paths"]) == 2
    assert all(
        p.startswith(f".madang/pages/{page}/blocks/") for p in entry["paths"]
    )
    contract.check(client.post(f"/trash/{entry['id']}/restore"), 200)
    assert pages.read_header(folder / "page.md")["blocks"] == [
        "b01",
        view["id"],
    ]
    assert json.loads((folder / "blocks/b01-base.json").read_text()) == {"a": 2}


def test_view_title_comes_from_title_field(
    client, home, page, contract
) -> None:
    contract.check(
        client.post(
            f"/pages/{page}/blocks",
            json={"type": "data", "name": "base", "content": '{"a": 1}'},
        ),
        201,
    )
    body = {
        "type": "view",
        "template": "resume@1",
        "bindings": {"base": "b01"},
    }
    titled = contract.check(
        client.post(
            f"/pages/{page}/blocks",
            json={**body, "name": "n1", "title": "이력서"},
        ),
        201,
    )
    named = contract.check(
        client.post(f"/pages/{page}/blocks", json={**body, "name": "n2"}), 201
    )
    folder = page_dir(home, page)
    titled_head, _ = frontmatter.read(folder / titled["file"])
    named_head, _ = frontmatter.read(folder / named["file"])
    assert titled_head["title"] == "이력서"
    assert "title" not in named_head


def test_message_blocks_are_read_only(
    client,
    home,
    page,
    contract,
) -> None:
    from madang.store.log import append_message

    append_message(page_dir(home, page), "user", "안녕", {"target": "page"})
    block = contract.check(client.get(f"/pages/{page}/blocks/b01"), 200)
    assert block["header"]["role"] == "user" and block["content"] == "안녕"
    contract.check(
        client.put(f"/pages/{page}/blocks/b01", json={"content": "x"}), 400
    )
    contract.check(
        client.patch(f"/pages/{page}/blocks/b01", json={"title": "x"}), 400
    )
    contract.check(client.delete(f"/pages/{page}/blocks/b01"), 204)
    folder = page_dir(home, page)
    assert pages.read_header(folder / "page.md")["blocks"] == []
    assert "안녕" in (folder / "page.md").read_text()


# 메모리


def test_memory_read_and_save(
    client, home, project_root, page, contract
) -> None:
    memory = contract.check(client.get(f"/pages/{page}/memory"), 200)
    assert memory["root"]["path"] == str(home.resolve() / "profile.md")
    assert memory["project"]["path"] == str(project_root / ".madang/brief.md")
    assert memory["project"]["layer"] == "project"
    assert memory["state"]["token_limit"] == 2000
    assert "token_limit" not in memory["root"]

    state = memory["state"]["content"].replace(
        "status: planning", "status: doing"
    )
    saved = contract.check(
        client.put(f"/pages/{page}/memory/state", json={"content": state}), 200
    )
    assert saved["content"] == state
    card = contract.check(client.get(PAGES), 200)[0]
    assert card["status"] == "doing"

    broken = contract.check(
        client.put(
            f"/pages/{page}/memory/state",
            json={"content": "---\nstatus: nope\n---\n"},
        ),
        400,
    )
    assert {i["code"] for i in broken["issues"]} >= {"invalid-value"}
    assert all(i["path"] == "ledger.md" for i in broken["issues"])
    assert "status: doing" in (page_dir(home, page) / "ledger.md").read_text()

    root = contract.check(
        client.put(
            f"/pages/{page}/memory/root", json={"content": "# 나\n한국어로.\n"}
        ),
        200,
    )
    assert root["tokens"] > 0
    assert (home / "profile.md").read_text() == "# 나\n한국어로.\n"
    notes = contract.check(
        client.put(
            f"/pages/{page}/memory/project", json={"content": "프로젝트 메모\n"}
        ),
        200,
    )
    assert notes["layer"] == "project"
    assert (project_root / ".madang/brief.md").read_text() == "프로젝트 메모\n"
    contract.check(
        client.put(
            f"/pages/{page}/memory/project", json={"content": "---\n: [\n---\n"}
        ),
        400,
    )
    for layer in ("space", "other"):
        contract.check(
            client.put(f"/pages/{page}/memory/{layer}", json={"content": "x"}),
            400,
        )


# 템플릿


def test_templates(client, home, contract, tmp_path, monkeypatch) -> None:
    listed = contract.check(client.get("/templates"), 200)
    assert {t["name"] for t in listed} == {
        "decisions",
        "resume",
        "table",
        "tasks",
    }
    contract.check(client.get("/templates/resume/schema"), 404)

    bundled = tmp_path / "bundled" / "resume"
    bundled.mkdir(parents=True)
    (bundled / "template.yaml").write_text(
        "name: resume\nversion: 1\ntitle: 이력서\n"
        "slots:\n  base: {schema: '#/base', required: true, label: 기본}\n"
        "editable: {text: true, style: [color.accent]}\n"
    )
    (bundled / "schema.json").write_text('{"base": {"type": "object"}}')
    monkeypatch.setenv("MADANG_TEMPLATES", str(tmp_path / "bundled"))
    installed = home / "templates" / "memo"
    installed.mkdir(parents=True)
    (installed / "template.yaml").write_text("name: memo\nversion: 2\n")

    listed = contract.check(client.get("/templates"), 200)
    by_name = {t["name"]: t for t in listed}
    assert (
        by_name["resume"]["title"] == "이력서" and by_name["resume"]["builtin"]
    )
    assert (
        by_name["memo"]["builtin"] is False and by_name["memo"]["version"] == 2
    )
    schema = contract.check(client.get("/templates/resume/schema"), 200)
    assert json.loads(schema["schema"]) == {"base": {"type": "object"}}
