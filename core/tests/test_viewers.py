import json
import subprocess
from pathlib import Path

import pytest
import yaml

from madang.viewers import (
    FOLLOW_PINNED,
    STATUS_BROKEN,
    STATUS_INVALID,
    STATUS_MISSING,
    STATUS_OK,
    Registry,
    ViewerError,
    ViewerWatcher,
    check,
    content_hash,
    document_context,
    find_views,
    load_manifest,
    parse_view_info,
    resolve_view,
    source_pin,
)

RESUME = Path(__file__).resolve().parents[2] / "templates/viewers/resume-basic"
SCHEMA = {
    "type": "object",
    "required": ["title"],
    "properties": {
        "title": {"type": "string"},
        "items": {"type": "array", "items": {"$ref": "#/$defs/item"}},
    },
    "$defs": {
        "item": {
            "type": "object",
            "required": ["n"],
            "additionalProperties": False,
            "properties": {"n": {"type": "integer"}},
        }
    },
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def make_viewer(
    folder: Path, name: str = "demo/list", body: str = "hi"
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "viewer.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "1.0.0",
                "schema": "schema.json",
                "entry": "index.html",
            }
        )
    )
    (folder / "schema.json").write_text(json.dumps(SCHEMA))
    (folder / "index.html").write_text(f"<!doctype html><p>{body}</p>")
    return folder


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def registry(home: Path) -> Registry:
    return Registry(home)


# 규격


def test_manifest_reads_fields(tmp_path: Path) -> None:
    manifest = load_manifest(make_viewer(tmp_path / "v"))
    assert manifest.name == "demo/list"
    assert manifest.version == "1.0.0"
    assert manifest.schema() == SCHEMA
    assert "<p>hi</p>" in manifest.entry_html()


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"name": "nonamespace"}, "name-invalid"),
        ({"name": "Demo/List"}, "name-invalid"),
        ({"entry": "../outside.html"}, "manifest-invalid"),
        ({"schema": "missing.json"}, "manifest-invalid"),
        ({"version": ""}, "manifest-invalid"),
    ],
)
def test_manifest_rejects_bad_fields(
    tmp_path: Path, change: dict, code: str
) -> None:
    folder = make_viewer(tmp_path / "v")
    data = json.loads((folder / "viewer.json").read_text())
    (folder / "viewer.json").write_text(json.dumps({**data, **change}))
    with pytest.raises(ViewerError) as err:
        load_manifest(folder)
    assert err.value.code == code


def test_manifest_missing(tmp_path: Path) -> None:
    with pytest.raises(ViewerError) as err:
        load_manifest(tmp_path)
    assert err.value.code == "manifest-missing"


def test_resume_example_follows_the_spec() -> None:
    manifest = load_manifest(RESUME)
    assert manifest.name == "resume/basic"
    sample = json.loads((RESUME / "sample.json").read_text())
    assert check(sample, manifest.schema()) == []


# 스키마


def test_schema_reports_every_path() -> None:
    data = {"items": [{"n": 1}, {"n": "2", "x": True}, "bad"]}
    issues = [(i.path, i.message) for i in check(data, SCHEMA)]
    assert issues == [
        ("title", "is required"),
        ("items[1].n", "expected integer, got string"),
        ("items[1].x", "is not allowed"),
        ("items[2]", "expected object, got string"),
    ]


def test_schema_type_details() -> None:
    assert check(True, {"type": "number"})[0].message == (
        "expected number, got boolean"
    )
    assert check(2.0, {"type": "integer"}) == []
    assert check(None, {"type": ["string", "null"]}) == []
    assert check("c", {"enum": ["a", "b"]})[0].path == ""
    with pytest.raises(ViewerError) as err:
        check({}, {"$ref": "#/$defs/none"})
    assert err.value.code == "schema-invalid"


# 등록부


def test_register_live_writes_reference_only(
    registry: Registry, home: Path, tmp_path: Path
) -> None:
    source = make_viewer(tmp_path / "src")
    entry = registry.register(source)
    assert entry.follow == "live" and entry.pinned is None
    text = registry.path.read_text()
    assert text.startswith("# ")
    assert yaml.safe_load(text) == [
        {"name": "demo/list", "source": str(source.resolve()), "follow": "live"}
    ]
    assert not (home / "cache").exists()
    assert registry.get("demo/list") == entry


def test_register_same_name_is_conflict(
    registry: Registry, tmp_path: Path
) -> None:
    registry.register(make_viewer(tmp_path / "a"))
    with pytest.raises(ViewerError) as err:
        registry.register(make_viewer(tmp_path / "b"))
    assert err.value.code == "name-conflict"


def test_register_rejects_unknown_follow(
    registry: Registry, tmp_path: Path
) -> None:
    with pytest.raises(ViewerError) as err:
        registry.register(make_viewer(tmp_path / "a"), follow="copy")
    assert err.value.code == "follow-invalid"


def test_unregister_keeps_source(registry: Registry, tmp_path: Path) -> None:
    source = make_viewer(tmp_path / "a")
    registry.register(source)
    registry.unregister("demo/list")
    assert registry.entries() == []
    assert (source / "viewer.json").is_file()
    with pytest.raises(ViewerError) as err:
        registry.get("demo/list")
    assert err.value.code == "not-found"


@pytest.mark.parametrize(
    "items",
    [
        {"name": "a/b"},
        [{"name": "a/b", "source": "/x", "follow": "pinned"}],
        [{"name": "a/b", "source": "/x", "follow": "live", "pinned": "abc"}],
        [{"name": "bad", "source": "/x", "follow": "live"}],
    ],
)
def test_invalid_registry_file(registry: Registry, items: object) -> None:
    registry.path.write_text(yaml.safe_dump(items))
    with pytest.raises(ViewerError) as err:
        registry.entries()
    assert err.value.code == "registry-invalid"


def test_duplicate_names_in_file_conflict(registry: Registry) -> None:
    item = {"name": "a/b", "source": "/x", "follow": "live"}
    registry.path.write_text(yaml.safe_dump([item, item]))
    with pytest.raises(ViewerError) as err:
        registry.entries()
    assert err.value.code == "name-conflict"


def test_missing_source_is_broken(registry: Registry, tmp_path: Path) -> None:
    source = make_viewer(tmp_path / "gone")
    entry = registry.register(source)
    assert registry.status(entry) == STATUS_OK
    for child in source.iterdir():
        child.unlink()
    source.rmdir()
    assert registry.status(entry) == STATUS_BROKEN
    resolved = registry.resolve("demo/list")
    assert resolved.status == STATUS_BROKEN
    assert "manifest-missing" in resolved.message


# pinned


def test_pinned_outside_git_uses_content_hash(
    registry: Registry, home: Path, tmp_path: Path
) -> None:
    source = make_viewer(tmp_path / "src")
    entry = registry.register(source, follow=FOLLOW_PINNED)
    assert entry.pinned == content_hash(source)
    copy = home / "cache" / entry.pinned / "demo/list"
    assert (copy / "index.html").read_text() == "<!doctype html><p>hi</p>"

    (source / "index.html").write_text("<p>changed</p>")
    resolved = registry.resolve("demo/list")
    assert resolved.origin == "cache"
    assert resolved.manifest.entry_html() == "<!doctype html><p>hi</p>"


def test_pinned_in_clean_git_uses_commit(
    registry: Registry, home: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@example.com")
    source = make_viewer(repo / "viewers" / "list")
    (repo / "other.txt").write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "viewer")
    commit = git(repo, "rev-parse", "HEAD").strip()
    (repo / "other.txt").write_text("y")
    git(repo, "commit", "-qam", "unrelated")

    assert source_pin(source) == commit
    entry = registry.register(source, follow=FOLLOW_PINNED)
    assert entry.pinned == commit
    assert (home / "cache" / commit / "demo/list/viewer.json").is_file()

    (source / "index.html").write_text("<p>dirty</p>")
    assert source_pin(source) == content_hash(source)


def test_repin_moves_to_new_hash(registry: Registry, tmp_path: Path) -> None:
    source = make_viewer(tmp_path / "src")
    first = registry.register(source, follow=FOLLOW_PINNED)
    (source / "index.html").write_text("<p>v2</p>")
    second = registry.repin("demo/list")
    assert second.pinned != first.pinned
    assert registry.get("demo/list").pinned == second.pinned
    old = registry.resolve("demo/list", pin=first.pinned[:8])
    assert old.status == STATUS_OK
    assert "hi" in old.manifest.entry_html()


def test_repin_requires_pinned(registry: Registry, tmp_path: Path) -> None:
    registry.register(make_viewer(tmp_path / "src"))
    with pytest.raises(ViewerError) as err:
        registry.repin("demo/list")
    assert err.value.code == "not-pinned"


def test_unknown_pin_is_broken(registry: Registry) -> None:
    resolved = registry.resolve("demo/list", pin="deadbeefcafe")
    assert resolved.status == STATUS_BROKEN


# 이름 해석


def test_project_viewer_wins_inside_project(
    registry: Registry, tmp_path: Path
) -> None:
    registry.register(make_viewer(tmp_path / "global", body="global"))
    project = tmp_path / "proj"
    make_viewer(project / ".madang/viewers/list", body="local")

    inside = registry.resolve("demo/list", project=project)
    assert inside.origin == "project"
    assert "local" in inside.manifest.entry_html()
    outside = registry.resolve("demo/list")
    assert outside.origin == "registry"
    assert "global" in outside.manifest.entry_html()


def test_project_viewers_with_same_name_conflict(
    registry: Registry, tmp_path: Path
) -> None:
    project = tmp_path / "proj"
    make_viewer(project / ".madang/viewers/a")
    make_viewer(project / ".madang/viewers/b")
    with pytest.raises(ViewerError) as err:
        registry.resolve("demo/list", project=project)
    assert err.value.code == "name-conflict"


def test_unregistered_name_is_missing(registry: Registry) -> None:
    assert registry.resolve("demo/none").status == STATUS_MISSING


# 감시


def test_watcher_reports_live_changes(
    registry: Registry, tmp_path: Path
) -> None:
    live = make_viewer(tmp_path / "live")
    pinned = make_viewer(tmp_path / "pinned", name="demo/pinned")
    registry.register(live)
    registry.register(pinned, follow=FOLLOW_PINNED)
    seen: list[str] = []
    watcher = ViewerWatcher(registry, seen.append)

    assert watcher.poll() == []
    (live / "index.html").write_text("<p>new and longer</p>")
    (pinned / "index.html").write_text("<p>new and longer</p>")
    assert watcher.poll() == ["demo/list"]
    assert watcher.poll() == []

    for child in live.iterdir():
        child.unlink()
    live.rmdir()
    assert watcher.poll() == ["demo/list"]
    assert seen == ["demo/list", "demo/list"]


def test_watcher_thread_starts_and_stops(
    registry: Registry, tmp_path: Path
) -> None:
    registry.register(make_viewer(tmp_path / "live"))
    watcher = ViewerWatcher(registry, lambda _: None, interval=0.01)
    watcher.start()
    watcher.stop()


# view 펜스


def test_parse_view_info() -> None:
    ref = parse_view_info("view resume/basic@1a2b3c4 data=./base.json")
    assert ref.key == "resume/basic@1a2b3c4 data=./base.json"
    assert (ref.name, ref.pin, ref.data) == (
        "resume/basic",
        "1a2b3c4",
        "./base.json",
    )
    assert parse_view_info("python") is None
    assert parse_view_info("viewer x") is None


def test_find_views_skips_front_matter_and_code() -> None:
    markdown = (
        "---\ntitle: x\n---\n"
        "```view a/b data=one.json\n```\n"
        "````md\n```view c/d\n```\n````\n"
        "~~~ view a/b   data=one.json\n~~~\n"
        "```view e/f\n```\n"
    )
    assert [v.key for v in find_views(markdown)] == [
        "a/b data=one.json",
        "e/f",
    ]


def test_document_context_statuses(registry: Registry, tmp_path: Path) -> None:
    registry.register(make_viewer(tmp_path / "v"))
    project = tmp_path / "proj"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (docs / "ok.json").write_text(json.dumps({"title": "t"}))
    (docs / "bad.yaml").write_text("items:\n  - n: one\n")
    markdown = (
        "```view demo/list data=ok.json\n```\n"
        "```view demo/list data=bad.yaml\n```\n"
        "```view demo/none data=ok.json\n```\n"
        "```view demo/list data=../../outside.json\n```\n"
        "```view demo/list data=missing.json\n```\n"
    )
    views = document_context(
        markdown, registry, document_dir=docs, project=project
    )["views"]
    ok = views["demo/list data=ok.json"]
    assert ok["status"] == STATUS_OK
    assert ok["data"] == {"title": "t"}
    assert "<p>hi</p>" in ok["html"]
    bad = views["demo/list data=bad.yaml"]
    assert bad["status"] == STATUS_INVALID and "html" not in bad
    assert [e["path"] for e in bad["errors"]] == ["title", "items[0].n"]
    assert views["demo/none data=ok.json"]["status"] == STATUS_MISSING
    assert views["demo/none data=ok.json"]["data"] == {"title": "t"}
    outside = views["demo/list data=../../outside.json"]
    assert "data-outside" in outside["message"]
    assert "data-invalid" in views["demo/list data=missing.json"]["message"]


def test_resume_example_resolves_with_sample(
    registry: Registry, tmp_path: Path
) -> None:
    registry.register(RESUME)
    ref = parse_view_info("view resume/basic data=sample.json")
    entry = resolve_view(ref, registry, document_dir=RESUME)
    assert entry.status == STATUS_OK
    assert entry.data["name"]
    assert "madang-view-data" in entry.html
