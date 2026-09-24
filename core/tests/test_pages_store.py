from datetime import date
from pathlib import Path

import pytest

from madang.store import frontmatter, pages, projects
from madang.store.home import init_home
from madang.validate import validate_target


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    init_home(home)
    return home


def project(home: Path, tmp_path: Path, name: str) -> projects.Project:
    (tmp_path / name).mkdir()
    return projects.add(home, tmp_path / name)


@pytest.fixture
def work(home: Path, tmp_path: Path) -> Path:
    return project(home, tmp_path, "work").pages_dir


def test_create_page_is_valid(home: Path, tmp_path: Path, work: Path) -> None:
    page = pages.create_page(work, "Lock Race", day=date(2026, 9, 24))
    assert page == (
        tmp_path.resolve() / "work/.madang/pages/2026-09-24-lock-race"
    )
    assert not (page / "log.md").exists() and (page / "blocks").is_dir()
    assert frontmatter.read(page / "ledger.md")[0]["reads"] == []
    assert validate_target(page) == []
    with pytest.raises(FileExistsError):
        pages.create_page(work, "Lock Race", day=date(2026, 9, 24))
    with pytest.raises(FileNotFoundError):
        pages.create_page(tmp_path / "missing", "x")


def test_find_page(home: Path, tmp_path: Path) -> None:
    a = project(home, tmp_path, "a")
    b = project(home, tmp_path, "b")
    page = pages.create_page(a.pages_dir, "one", day=date(2026, 9, 24))
    assert pages.find_page(home, "2026-09-24-one") == page
    with pytest.raises(pages.PageNotFoundError):
        pages.find_page(home, "2026-09-24-none")
    with pytest.raises(pages.PageNotFoundError):
        pages.find_page(home, "../a")
    pages.create_page(b.pages_dir, "one", day=date(2026, 9, 24))
    with pytest.raises(pages.PageNotFoundError, match="more than one project"):
        pages.find_page(home, "2026-09-24-one")
    projects.remove(home, "b")
    assert pages.find_page(home, "2026-09-24-one") == page


def test_move_page(home: Path, tmp_path: Path, work: Path) -> None:
    other = project(home, tmp_path, "other")
    page = pages.create_page(work, "p", day=date(2026, 9, 24))
    moved = pages.move_page(page, other.pages_dir)
    assert moved == other.pages_dir / page.name
    assert (moved / "page.md").is_file() and not page.exists()
    again = pages.create_page(work, "p", day=date(2026, 9, 24))
    with pytest.raises(FileExistsError):
        pages.move_page(again, other.pages_dir)


def test_update_state_keeps_body(work: Path) -> None:
    page = pages.create_page(work, "p")
    state = page / "ledger.md"
    body = (
        frontmatter.split(state.read_text(encoding="utf-8")).body
        + "\n추가 본문\r\n끝"
    )
    state.write_text(
        "---\nstatus: doing\nkind: build\ntier: 1\nattempts: 0\n---\n" + body,
        encoding="utf-8",
    )
    pages.update_state(page, lambda h: h.update(attempts=1))
    parts = frontmatter.split(state.read_bytes().decode("utf-8"))
    assert parts.body == body
    assert frontmatter.load_header(parts)["attempts"] == 1


def test_block_ids_grow_and_are_not_reused(work: Path) -> None:
    page = pages.create_page(work, "p")
    assert pages.allocate_block(page) == "b01"
    header, _ = frontmatter.read(page / "page.md")
    head = "<!-- b02 | 2026-09-24T08:00:00+09:00 | user | target=page -->"
    (page / "page.md").write_text(frontmatter.dumps(header, f"{head}\nhi\n"))
    (page / "blocks" / "b04-x.json").write_text("{}")
    assert pages.allocate_block(page) == "b05"
    (page / "blocks" / "b04-x.json").unlink()
    assert pages.allocate_block(page) == "b06"
    pages.append_block(page, "b06")
    pages.append_block(page, "b06")
    assert frontmatter.read(page / "page.md")[0]["blocks"] == ["b06"]
    assert validate_target(page) == []


def test_block_files_skip_sidecars(work: Path) -> None:
    page = pages.create_page(work, "p")
    blocks = page / "blocks"
    for name in ("b03-cv.json", "b03-cv.meta.yaml", "b30-other.md"):
        (blocks / name).write_text("x")
    assert [p.name for p in pages.block_files(page, "b03")] == ["b03-cv.json"]
    assert pages.block_files(page, "nope") == []
