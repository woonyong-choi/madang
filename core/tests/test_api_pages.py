"""공간·페이지·블록·메모리·휴지통·템플릿 경로."""

import json

from api_support import git, page_dir, subjects

from madang.store import frontmatter, pages, runs


def clean(home) -> bool:
    return git(home, "status", "--porcelain") == ""


# 공간


def test_space_lifecycle(client, home, contract) -> None:
    created = contract.check(
        client.post(
            "/spaces",
            json={"slug": "jobs", "title": "지원", "color": "#3a5bd9"},
        ),
        201,
    )
    assert created["color"] == "#3a5bd9" and created["pages"] == 0
    contract.check(
        client.post("/spaces", json={"slug": "jobs", "title": "x"}), 409
    )
    contract.check(
        client.post("/spaces", json={"slug": "Bad Slug", "title": "x"}), 400
    )
    contract.check(
        client.post(
            "/spaces", json={"slug": "sub", "title": "x", "parent": "nope"}
        ),
        404,
    )
    contract.check(
        client.post(
            "/spaces", json={"slug": "sub", "title": "하위", "parent": "jobs"}
        ),
        201,
    )

    updated = contract.check(
        client.patch(
            "/spaces/jobs", json={"title": "지원 2026", "sort": "title"}
        ),
        200,
    )
    assert updated["title"] == "지원 2026" and updated["sort"] == "title"
    contract.check(client.patch("/spaces/jobs", json={"parent": "sub"}), 400)
    cleared = contract.check(
        client.patch("/spaces/jobs", json={"color": None}), 200
    )
    assert "color" not in cleared
    contract.check(client.patch("/spaces/nope", json={"title": "x"}), 404)

    listed = contract.check(client.get("/spaces"), 200)
    assert [s["slug"] for s in listed] == ["jobs", "root", "sub"]

    contract.check(client.delete("/spaces/jobs"), 409)  # 하위 공간
    contract.check(client.delete("/spaces/sub"), 204)
    contract.check(client.delete("/spaces/root"), 409)
    client.post("/spaces/jobs/pages", json={"title": "이력서"})
    assert contract.check(client.delete("/spaces/jobs"), 409)["message"]
    assert clean(home)
    assert "[sub] delete space" in subjects(home)


# 페이지


def test_create_and_list_pages(client, home, contract) -> None:
    detail = contract.check(
        client.post(
            "/spaces/root/pages", json={"title": "이력서", "kind": "design"}
        ),
        201,
    )
    assert detail["kind"] == "design" and detail["blocks"] == []
    contract.check(
        client.post("/spaces/root/pages", json={"title": "이력서"}), 409
    )
    contract.check(
        client.post("/spaces/root/pages", json={"title": "x", "kind": "z"}),
        400,
    )
    contract.check(client.post("/spaces/nope/pages", json={"title": "x"}), 404)
    second = client.post("/spaces/root/pages", json={"title": "공고 분석"})
    pinned = second.json()["id"]
    contract.check(client.patch(f"/pages/{pinned}", json={"pinned": True}), 200)

    cards = contract.check(client.get("/spaces/root/pages"), 200)
    assert [c["id"] for c in cards] == [pinned, detail["id"]]
    assert cards[1]["status"] == "planning"
    assert "last_run" not in cards[1]
    contract.check(client.get("/spaces/nope/pages"), 404)
    assert clean(home)
    assert subjects(home)[-2] == f"[{detail['id']}] create page"


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

    card = contract.check(client.get("/spaces/root/pages"), 200)[0]
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
    page,
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
    contract.check(client.patch(f"/pages/{page}", json={"space": "nope"}), 404)

    client.post("/spaces", json={"slug": "jobs", "title": "지원"})
    moved = contract.check(
        client.patch(f"/pages/{page}", json={"space": "jobs"}), 200
    )
    assert moved["space"] == "jobs"
    assert (home / "spaces/jobs/pages" / page / "page.md").is_file()
    assert not (home / "spaces/root/pages" / page).exists()
    assert clean(home)
    assert subjects(home)[0] == f"[{page}] move to jobs"


def test_delete_page_and_restore_from_trash(
    client,
    home,
    page,
    contract,
) -> None:
    contract.check(client.delete(f"/pages/{page}"), 204)
    contract.check(client.get(f"/pages/{page}"), 404)
    contract.check(client.delete(f"/pages/{page}"), 404)
    assert subjects(home)[0] == f"[{page}] delete page"

    trash = contract.check(client.get("/trash"), 200)
    assert len(trash) == 1
    entry = trash[0]
    assert entry["page"] == page and entry.get("block") is None
    assert entry["paths"] == [f"spaces/root/pages/{page}"]

    contract.check(client.post("/trash/zzzz/restore"), 404)
    restored = contract.check(
        client.post(f"/trash/{entry['commit']}/restore"), 200
    )
    assert restored["paths"] == entry["paths"]
    contract.check(client.get(f"/pages/{page}"), 200)
    assert contract.check(client.get("/trash"), 200) == []
    assert subjects(home)[0] == f"[{page}] restore page"
    assert clean(home)


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
    assert subjects(home)[0] == f"[{page}] edit b01"

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
    assert subjects(home)[0] == f"[{page}] delete b01"
    assert clean(home)

    entry = contract.check(client.get("/trash"), 200)[0]
    assert entry["block"] == "b01" and len(entry["paths"]) == 2
    contract.check(client.post(f"/trash/{entry['commit']}/restore"), 200)
    assert pages.read_header(folder / "page.md")["blocks"] == [
        "b01",
        view["id"],
    ]
    assert json.loads((folder / "blocks/b01-base.json").read_text()) == {"a": 2}
    assert clean(home)


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
    assert "안녕" in (folder / "log.md").read_text()


# 메모리


def test_memory_read_and_save(client, home, page, contract) -> None:
    memory = contract.check(client.get(f"/pages/{page}/memory"), 200)
    assert memory["root"]["path"] == "root.md"
    assert memory["space"]["path"] == "spaces/root/space.md"
    assert memory["state"]["token_limit"] == 2000
    assert "token_limit" not in memory["root"]

    state = memory["state"]["content"].replace(
        "status: planning", "status: doing"
    )
    saved = contract.check(
        client.put(f"/pages/{page}/memory/state", json={"content": state}), 200
    )
    assert saved["content"] == state
    assert subjects(home)[0] == f"[{page}] edit state.md"
    card = contract.check(client.get("/spaces/root/pages"), 200)[0]
    assert card["status"] == "doing"

    broken = contract.check(
        client.put(
            f"/pages/{page}/memory/state",
            json={"content": "---\nstatus: nope\n---\n"},
        ),
        400,
    )
    assert {i["code"] for i in broken["issues"]} >= {"invalid-value"}
    assert all(i["path"] == "state.md" for i in broken["issues"])
    assert "status: doing" in (page_dir(home, page) / "state.md").read_text()

    root = contract.check(
        client.put(
            f"/pages/{page}/memory/root", json={"content": "# 나\n한국어로.\n"}
        ),
        200,
    )
    assert root["tokens"] > 0
    assert subjects(home)[0] == "[home] edit root.md"
    contract.check(
        client.put(
            f"/pages/{page}/memory/space", json={"content": "---\n: [\n---\n"}
        ),
        400,
    )
    contract.check(
        client.put(f"/pages/{page}/memory/other", json={"content": "x"}), 400
    )
    assert clean(home)


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
    installed.mkdir()
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
