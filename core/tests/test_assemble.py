import json
from pathlib import Path

import pytest

from madang import assemble as asm
from madang import contract
from madang.config import load_config
from madang.store import frontmatter, pages, projects
from madang.store.home import init_home
from madang.validate import tokens


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("MADANG_TEMPLATES", raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    init_home(root)
    (root / "root.md").write_text("ROOT-NOTES\n")
    (tmp_path / "work").mkdir()
    project = projects.add(root, tmp_path / "work")
    project.memory.write_text("PROJECT-NOTES\n")
    return root


@pytest.fixture
def page(home: Path) -> Path:
    pages_dir = projects.get(home, "work").pages_dir
    page_dir = pages.create_page(pages_dir, "Resume", slug="resume")
    state = page_dir / "state.md"
    text = state.read_text()
    text = text.replace("## 막힌 점\n", "## 막힌 점\nBLOCKED-NOTE\n")
    text = text.replace("## 로그\n", "## 로그\nLOG-LINE\n")
    state.write_text(text)
    return page_dir


def build(page: Path, home: Path, **kw):
    cfg = load_config(home)
    args = {"target": None, "request": "REQUEST-TEXT", "tier": 1}
    args.update(kw)
    return asm.assemble(
        page,
        args["target"],
        args["request"],
        args["tier"],
        cfg=cfg,
        runner=args.get("runner", "claude"),
    )


def set_limit(home: Path, tokens: int) -> None:
    path = home / "config/madang.yaml"
    path.write_text(
        path.read_text().replace(
            "block_input_tokens: 4000", f"block_input_tokens: {tokens}"
        )
    )


def test_parts_follow_the_fixed_order(home: Path, page: Path) -> None:
    (page / "blocks/b01-plan.md").write_text("TARGET-BODY\n")
    out = build(page, home, target="b01")
    names = [p.name for p in out.parts]
    assert names == [
        "root",
        "project",
        "state",
        "contract",
        "target",
        "request",
    ]
    markers = [
        "ROOT-NOTES",
        "PROJECT-NOTES",
        "BLOCKED-NOTE",
        "너는 Madang 페이지",
        "TARGET-BODY",
        "REQUEST-TEXT",
    ]
    positions = [out.prompt.index(m) for m in markers]
    assert positions == sorted(positions)


def test_estimate_adds_parts_and_system(home: Path, page: Path) -> None:
    out = build(page, home)
    record = out.estimate()
    parts = record["parts"]
    assert parts["system_est"] == 23000
    assert set(parts) == {
        "system_est",
        "root",
        "project",
        "state",
        "contract",
        "request",
    }
    assert record["total_est"] == sum(parts.values()) == out.total_est
    for part in out.parts:
        assert part.tokens == tokens.count_tokens(part.text)
    assert record["tokenizer"] == "cl100k_base"
    assert "truncated" not in record
    json.dumps(record)


def test_system_estimate_comes_from_runners_yaml(
    home: Path, page: Path
) -> None:
    path = home / "config/runners.yaml"
    path.write_text(
        path.read_text().replace(
            "  system_est: 23000\n", "  system_est: 12345\n"
        )
    )
    assert build(page, home).system_est == 12345
    assert build(page, home, runner="other").system_est == 0


def test_system_estimate_falls_back_to_bundled_runners(
    home: Path, page: Path
) -> None:
    path = home / "config/runners.yaml"
    path.write_text(path.read_text().replace("  system_est: 24000\n", ""))
    assert build(page, home, runner="codex").system_est == 24000


def test_contract_is_rendered(home: Path, page: Path) -> None:
    out = build(page, home)
    text = next(p.text for p in out.parts if p.name == "contract")
    assert out.contract == contract.VERSION == "v1"
    assert 'version="v1"' in text
    for placeholder in ("{repo}", "{page}", "{templates}", "{n}"):
        assert placeholder not in text
    assert f"작업 폴더는 {page.parents[2]}이다" in text
    assert f"{page}/blocks/" in text
    assert "resume" in text and "table" in text
    assert "2회 연속 실패" in text


def test_project_without_memory_is_empty(home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "code"
    repo.mkdir()
    project = projects.add(home, repo)
    project.memory.unlink()
    page_dir = pages.create_page(project.pages_dir, "Task", slug="task")
    out = build(page_dir, home)
    assert f"작업 폴더는 {repo.resolve()}이다" in out.prompt
    assert next(p for p in out.parts if p.name == "project").text == (
        "<project>\n\n</project>"
    )


def test_target_block_is_cut_at_the_limit(home: Path, page: Path) -> None:
    set_limit(home, 50)
    body = " ".join(f"word{i}" for i in range(2000))
    (page / "blocks/b02-long.md").write_text(body)
    out = build(page, home, target="b02")
    assert out.truncated == ["blocks/b02-long.md"]
    assert out.estimate()["truncated"] == ["blocks/b02-long.md"]
    target = next(p.text for p in out.parts if p.name == "target")
    kept = target.split("\n", 2)[2].rsplit("\n</file>", 1)[0]
    assert kept.startswith("word0 word1")
    assert kept.endswith(asm.TRUNCATION_MARK)
    assert tokens.count_tokens(kept) <= 50


def test_truncate_keeps_short_text() -> None:
    assert asm.truncate("short", 10) == ("short", False)
    cut, was_cut = asm.truncate("a " * 500, 20)
    assert was_cut and tokens.count_tokens(cut) <= 20


def test_view_target_brings_bound_data(home: Path, page: Path) -> None:
    (page / "blocks/b03-cv.json").write_text('{"name": "DATA-VALUE"}')
    (page / "blocks/b03-cv.meta.yaml").write_text("type: data\n")
    view = {"type": "view", "template": "resume@1", "bindings": {"base": "b03"}}
    (page / "blocks/b04-cv.view.md").write_text(frontmatter.dumps(view, ""))
    out = build(page, home, target="b04")
    target = next(p.text for p in out.parts if p.name == "target")
    assert 'path="blocks/b04-cv.view.md"' in target
    assert 'path="blocks/b03-cv.json"' in target
    assert "DATA-VALUE" in target
    assert "meta.yaml" not in target


def test_missing_target_is_refused(home: Path, page: Path) -> None:
    with pytest.raises(ValueError, match="b09"):
        build(page, home, target="b09")


def test_promoted_run_reads_only_blocked_and_next(
    home: Path, page: Path
) -> None:
    first = build(page, home, tier=1)
    assert "LOG-LINE" in first.prompt and "## 목표" in first.prompt
    promoted = build(page, home, tier=2)
    state = next(p.text for p in promoted.parts if p.name == "state")
    assert "## 막힌 점" in state and "BLOCKED-NOTE" in state
    assert "## 다음 할 일" in state
    assert "LOG-LINE" not in state
    assert "## 목표" not in state
    assert "status:" not in state


def test_tokenizer_fallback_is_marked(
    home: Path, page: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exact = build(page, home)
    monkeypatch.setattr(tokens, "_encoding", lambda: None)
    rough = build(page, home)
    assert tokens.uses_fallback()
    assert tokens.tokenizer_name() == tokens.FALLBACK_TOKENIZER
    assert rough.estimate()["tokenizer"] == "utf8-bytes/3"
    # UTF-8 3바이트당 토큰 1개로 센다. state 검사와 같은 기준이다
    request = next(p for p in rough.parts if p.name == "request")
    assert request.tokens == -(-len(request.text.encode()) // 3)
    assert tokens.count_tokens("가나다") == 3
    assert rough.total_est != exact.total_est
