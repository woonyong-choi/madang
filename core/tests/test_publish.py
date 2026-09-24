import functools
import json
import os
import re
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from madang.cli import app
from madang.publish import (
    SITE_MANIFEST,
    PublishError,
    build,
    collect,
    list_fences,
    parse_target,
    publish,
    undo,
)
from madang.recorder import published
from madang.viewers import Registry, content_hash

REPO = Path(__file__).resolve().parents[2]
RENDERER = REPO / "templates/_runtime/document.js"
NODE_MODULES = REPO / "templates/_tests/node_modules"
FIXTURES = Path(__file__).parent / "fixtures"
FENCE_CASES = json.loads((FIXTURES / "views/fences.json").read_text())
VIEWER_HTML = """<!doctype html><html><head></head><body><p id="out"></p>
<script>
var data = JSON.parse(document.getElementById('madang-view-data').textContent);
document.getElementById('out').textContent =
    data.title + ' items: ' + data.items.length;
</script></body></html>
"""
GUIDE = """---
title: 안내서
---
# Guide

[다른 문서](./other.md)

```view demo/list data=./list.json
```

- 목록 안 뷰어

  ```view none/here
  ```
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def make_viewer(folder: Path, name: str = "demo/list") -> Path:
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
    (folder / "schema.json").write_text(
        json.dumps({"type": "object", "required": ["title", "items"]})
    )
    (folder / "index.html").write_text(VIEWER_HTML)
    return folder


def write_config(root: Path, **publish_settings: object) -> None:
    path = root / ".madang/config.yaml"
    data = yaml.safe_load(path.read_text()) if path.is_file() else {}
    data = data or {}
    data["publish"] = publish_settings
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "guide.md").write_text(GUIDE)
    (docs / "other.md").write_text("# Other\n\n본문\n")
    (docs / "list.json").write_text(
        json.dumps({"title": "목록", "items": [1, 2]})
    )
    (docs / ".draft.md").write_text("# 숨김\n")
    (root / "notes.txt").write_text("not published\n")
    make_viewer(root / ".madang/viewers/list")
    write_config(root, include=["docs"], target="folder:../site")
    return root


def page_json(page: Path, element: str) -> object:
    found = re.search(
        rf'<script type="application/json" id="{element}">(.*?)</script>',
        page.read_text(),
        re.S,
    )
    assert found is not None
    return json.loads(found.group(1))


# view 펜스 목록: 렌더러 listViews()와 같은 사례를 쓴다.


@pytest.mark.parametrize("case", FENCE_CASES, ids=lambda c: c["name"])
def test_list_fences_matches_shared_cases(case: dict) -> None:
    assert [ref.key for ref in list_fences(case["markdown"])] == case["keys"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is missing")
def test_renderer_list_views_matches_shared_cases() -> None:
    out = subprocess.run(
        [
            "node",
            str(FIXTURES / "views/list_views.js"),
            str(RENDERER),
            str(FIXTURES / "views/fences.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(out) == [case["keys"] for case in FENCE_CASES]


# 설정과 포함 경로


def test_parse_target(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    assert parse_target("gh-pages", root).branch == "gh-pages"
    folder = parse_target("folder:../site", root).folder
    assert folder == (tmp_path / "site").resolve()
    for raw, code in [
        (None, "target-missing"),
        ("s3", "target-invalid"),
        ("folder:", "target-invalid"),
        ("folder:.", "target-invalid"),
        ("folder:..", "target-invalid"),
    ]:
        with pytest.raises(PublishError) as caught:
            parse_target(raw, root)
        assert caught.value.code == code


def test_collect_skips_hidden_and_excluded(project: Path) -> None:
    (project / "docs/out").mkdir()
    (project / "docs/out/old.html").write_text("x")
    found = collect(project, ["docs", "notes.txt"], [project / "docs/out"])
    assert found == [
        "docs/guide.md",
        "docs/list.json",
        "docs/other.md",
        "notes.txt",
    ]


@pytest.mark.parametrize(
    ("include", "code"),
    [
        ([], "include-empty"),
        (["missing"], "include-missing"),
        (["../outside"], "include-outside"),
    ],
)
def test_collect_rejects_bad_include(
    project: Path, include: list[str], code: str
) -> None:
    (project.parent / "outside").mkdir()
    with pytest.raises(PublishError) as caught:
        collect(project, include, [])
    assert caught.value.code == code


# 사이트


def test_build_site_embeds_markdown_context_and_pinned_viewer(
    project: Path, home: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    site = build(project, ["docs"], out=out, registry=Registry(home))

    pin = content_hash(project / ".madang/viewers/list")
    assert [d.page for d in site.documents] == [
        "docs/guide.html",
        "docs/other.html",
    ]
    assert site.documents[0].title == "안내서"
    assert [(v.name, v.pin) for v in site.viewers] == [("demo/list", pin)]
    assert site.warnings == [
        "docs/guide.md: view none/here: viewer 'none/here' is not registered"
    ]
    for rel in ("index.html", ".nojekyll", "docs/guide.md", "docs/list.json"):
        assert (out / rel).is_file()
    assert not (out / "docs/.draft.md").exists()
    assert not (out / ".madang").exists()
    assert not (out / "notes.txt").exists()
    assert (out / "_madang/runtime/document.js").read_bytes() == (
        RENDERER.read_bytes()
    )
    assert (out / f"_madang/viewers/{pin}/demo/list/viewer.json").is_file()

    guide = out / "docs/guide.html"
    assert '<script src="../_madang/runtime/document.js">' in (
        guide.read_text()
    )
    assert page_json(guide, "madang-markdown") == GUIDE
    views = page_json(guide, "madang-context")["views"]
    entry = views["demo/list data=./list.json"]
    assert entry["status"] == "ok"
    assert entry["pin"] == pin
    assert entry["data"] == {"title": "목록", "items": [1, 2]}
    assert entry["html"] == VIEWER_HTML
    assert views["none/here"]["status"] == "missing"

    manifest = json.loads((out / SITE_MANIFEST).read_text())
    assert manifest["viewers"] == [{"name": "demo/list", "pin": pin}]
    assert manifest["documents"][0]["page"] == "docs/guide.html"
    assert len(manifest["renderer"]) == 64


def test_build_rejects_page_over_included_html(
    project: Path, home: Path, tmp_path: Path
) -> None:
    (project / "docs/other.html").write_text("<p>x</p>")
    with pytest.raises(PublishError) as caught:
        build(project, ["docs"], out=tmp_path / "out", registry=Registry(home))
    assert caught.value.code == "path-conflict"


def test_build_pins_registered_git_viewer_to_its_commit(
    project: Path, home: Path, tmp_path: Path
) -> None:
    source = tmp_path / "viewers-repo"
    make_viewer(source / "shared", name="lib/shared")
    git(source, "init", "-q")
    git(source, "config", "user.name", "t")
    git(source, "config", "user.email", "t@t")
    git(source, "add", ".")
    git(source, "commit", "-qm", "viewer")
    Registry(home).register(source / "shared")
    (project / "docs/other.md").write_text(
        "# Other\n\n```view lib/shared data=./list.json\n```\n"
    )
    out = tmp_path / "out"
    site = build(project, ["docs"], out=out, registry=Registry(home))
    commit = git(source, "rev-parse", "HEAD")
    assert ("lib/shared", commit) in [(v.name, v.pin) for v in site.viewers]
    assert (out / f"_madang/viewers/{commit}/lib/shared/index.html").is_file()


# 폴더 대상


def test_publish_folder_records_and_undoes(
    project: Path, home: Path, tmp_path: Path
) -> None:
    target = tmp_path / "site"
    first = publish(project, home)
    assert first.record is not None and first.record.n == 1
    assert first.record.before == {}
    assert (target / "docs/guide.html").is_file()
    assert published.digests(target) == first.record.after
    assert (project / ".madang/published/1.json").is_file()

    assert publish(project, home).record is None  # 이미 같다

    (project / "docs/other.md").write_text("# Other\n\n바뀐 본문\n")
    (project / "docs/guide.md").unlink()
    second = publish(project, home)
    assert second.record is not None and second.record.n == 2
    assert not (target / "docs/guide.html").exists()

    assert undo(project).record.n == 2
    assert published.digests(target) == first.record.after
    assert undo(project).record.n == 1
    assert published.digests(target) == {}
    with pytest.raises(PublishError) as caught:
        undo(project)
    assert caught.value.code == "nothing-to-undo"


def test_publish_folder_refuses_foreign_folder(
    project: Path, home: Path, tmp_path: Path
) -> None:
    target = tmp_path / "site"
    target.mkdir()
    (target / "keep.txt").write_text("mine")
    with pytest.raises(PublishError) as caught:
        publish(project, home)
    assert caught.value.code == "target-not-site"
    assert os.listdir(target) == ["keep.txt"]


def test_undo_folder_refuses_changed_target(
    project: Path, home: Path, tmp_path: Path
) -> None:
    publish(project, home)
    (tmp_path / "site/docs/other.html").write_text("edited by hand")
    with pytest.raises(PublishError) as caught:
        undo(project)
    assert caught.value.code == "target-changed"


def test_publish_excludes_target_folder_inside_include(
    project: Path, home: Path
) -> None:
    write_config(project, include=["docs"], target="folder:docs/site")
    publish(project, home)
    (project / "docs/other.md").write_text("# Other\n\n다시\n")
    publish(project, home)
    assert not (project / "docs/site/docs/site").exists()


# gh-pages 대상


@pytest.fixture
def repo(project: Path, tmp_path: Path) -> Path:
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.name", "t")
    git(project, "config", "user.email", "t@t")
    git(project, "add", "docs", "notes.txt")
    git(project, "commit", "-qm", "init")
    write_config(project, include=["docs"], target="gh-pages")
    return project


@pytest.fixture
def remote(repo: Path, tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    return bare


def test_publish_gh_pages_pushes_and_undoes(
    repo: Path, remote: Path, home: Path
) -> None:
    head, status = git(repo, "rev-parse", "HEAD"), git(repo, "status", "-s")
    first = publish(repo, home)
    record = first.record
    assert record is not None and first.push_error is None
    assert record.branch == "gh-pages" and record.before_commit is None
    assert record.pushed_to == "origin"
    assert git(repo, "rev-parse", "gh-pages") == record.after_commit
    assert git(remote, "rev-parse", "gh-pages") == record.after_commit
    files = git(repo, "ls-tree", "-r", "--name-only", "gh-pages").split()
    assert {"index.html", ".nojekyll", "docs/guide.html", SITE_MANIFEST} <= (
        set(files)
    )
    # 작업 트리·인덱스·HEAD는 그대로다.
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "-s") == status

    assert publish(repo, home).record is None
    (repo / "docs/other.md").write_text("# Other\n\n두 번째\n")
    second = publish(repo, home).record
    assert second is not None
    assert git(repo, "rev-parse", f"{second.after_commit}^") == (
        record.after_commit
    )

    undone = undo(repo).record
    tip = git(repo, "rev-parse", "gh-pages")
    assert undone.undo_commit == tip
    assert git(repo, "rev-parse", "gh-pages^") == second.after_commit
    assert git(repo, "rev-parse", "gh-pages^{tree}") == git(
        repo, "rev-parse", f"{record.after_commit}^{{tree}}"
    )
    assert git(remote, "rev-parse", "gh-pages") == tip

    undo(repo)
    assert git(repo, "ls-tree", "gh-pages") == ""
    assert git(remote, "rev-parse", "gh-pages") == git(
        repo, "rev-parse", "gh-pages"
    )


def test_undo_gh_pages_refuses_changed_branch(repo: Path, home: Path) -> None:
    publish(repo, home)
    git(repo, "checkout", "-q", "gh-pages")
    (repo / "extra.txt").write_text("x")
    git(repo, "add", "extra.txt")
    git(repo, "commit", "-qm", "hand edit")
    git(repo, "checkout", "-q", "main")
    with pytest.raises(PublishError) as caught:
        undo(repo)
    assert caught.value.code == "target-changed"


def test_publish_gh_pages_without_remote_stays_local(
    repo: Path, home: Path
) -> None:
    record = publish(repo, home).record
    assert record is not None and record.pushed_to is None


def test_publish_gh_pages_push_denied_by_policy(
    repo: Path, remote: Path, home: Path
) -> None:
    config = yaml.safe_load((repo / ".madang/config.yaml").read_text())
    config["policy"] = {"deny": ["push"]}
    (repo / ".madang/config.yaml").write_text(yaml.safe_dump(config))
    record = publish(repo, home).record
    assert record is not None and record.pushed_to is None
    assert git(remote, "branch", "--list") == ""


def test_publish_gh_pages_force_rule_does_not_block_push(
    repo: Path, remote: Path, home: Path
) -> None:
    config = yaml.safe_load((repo / ".madang/config.yaml").read_text())
    config["policy"] = {"deny": ["push --force", "reset --hard"]}
    (repo / ".madang/config.yaml").write_text(yaml.safe_dump(config))
    record = publish(repo, home).record
    assert record is not None and record.pushed_to == "origin"


def test_publish_gh_pages_requires_repository(
    project: Path, home: Path
) -> None:
    write_config(project, include=["docs"], target="gh-pages")
    with pytest.raises(PublishError) as caught:
        publish(project, home)
    assert caught.value.code == "not-a-repository"


# 명령줄


def test_cli_publish_and_undo(project: Path, home: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--home", str(home)]).exit_code == 0
    added = runner.invoke(
        app,
        ["project", "add", str(project), "--id", "proj", "--home", str(home)],
    )
    assert added.exit_code == 0, added.output
    base = ["publish", "--project", "proj", "--home", str(home)]

    done = runner.invoke(app, base)
    assert done.exit_code == 0, done.output
    assert done.stdout.startswith("published 1 · folder:../site")
    assert "view none/here" in done.stderr

    again = runner.invoke(app, base)
    assert again.stdout.startswith("unchanged")
    back = runner.invoke(app, [*base, "--undo"])
    assert back.exit_code == 0, back.output
    assert back.stdout.startswith("undid publish 1")

    missing = runner.invoke(app, ["publish", "--home", str(home)], env={})
    assert missing.exit_code == 1


# 브라우저: 게시한 사이트를 열어 렌더러가 그린 문서를 본다.


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.mark.skipif(
    shutil.which("node") is None
    or not (NODE_MODULES / "@playwright/test").is_dir(),
    reason="node or templates/_tests playwright is not installed",
)
def test_published_site_renders_in_browser(
    project: Path, home: Path, tmp_path: Path
) -> None:
    publish(project, home)
    site = tmp_path / "site"
    handler = functools.partial(_QuietHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    web = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        out = subprocess.run(
            [
                "node",
                str(FIXTURES / "publish/open_site.js"),
                (site / "docs/guide.html").as_uri(),
                f"{web}/docs/guide.html",
                f"{web}/index.html",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "NODE_PATH": str(NODE_MODULES)},
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
    assert out.returncode == 0, out.stderr
    local, served, index = json.loads(out.stdout)
    for page in (local, served):
        assert page["heading"] == "Guide"
        assert page["frames"] == 1
        assert page["viewText"] == "목록 items: 2"
        assert page["fallbacks"] == ["missing"]
        assert page["links"] == ["./other.html"]
        assert page["outside"] == []
        assert page["errors"] == []
    assert index["heading"] == "proj"
    assert index["links"] == ["docs/guide.html", "docs/other.html"]
