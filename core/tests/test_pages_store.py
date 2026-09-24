from datetime import date
from pathlib import Path

import pytest

from madang.store import frontmatter, pages
from madang.store.home import init_home
from madang.validate import validate_target


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    init_home(home)
    return home


def test_create_space_and_page_are_valid(home: Path) -> None:
    pages.create_space(home, "work", title="Work")
    page = pages.create_page(home, "work", "Lock Race", day=date(2026, 9, 24))
    assert page == home / "spaces" / "work" / "pages" / "2026-09-24-lock-race"
    assert (page / "log.md").is_file() and (page / "blocks").is_dir()
    assert validate_target(page) == []
    with pytest.raises(FileExistsError):
        pages.create_page(home, "work", "Lock Race", day=date(2026, 9, 24))
    with pytest.raises(FileNotFoundError):
        pages.create_page(home, "missing", "x")


def test_find_page(home: Path) -> None:
    pages.create_space(home, "a")
    pages.create_space(home, "b")
    page = pages.create_page(home, "a", "one", day=date(2026, 9, 24))
    assert pages.find_page(home, "2026-09-24-one") == page
    with pytest.raises(pages.PageNotFound):
        pages.find_page(home, "2026-09-24-none")
    with pytest.raises(pages.PageNotFound):
        pages.find_page(home, "../a")
    pages.create_page(home, "b", "one", day=date(2026, 9, 24))
    with pytest.raises(pages.PageNotFound, match="more than one space"):
        pages.find_page(home, "2026-09-24-one")


def test_update_state_keeps_body(home: Path) -> None:
    pages.create_space(home, "work")
    page = pages.create_page(home, "work", "p")
    state = page / "state.md"
    body = frontmatter.split(state.read_text(encoding="utf-8")).body + "\n추가 본문\r\n끝"
    state.write_text("---\nstatus: doing\nkind: build\ntier: 1\nattempts: 0\n---\n" + body, encoding="utf-8")
    pages.update_state(page, lambda h: h.update(attempts=1))
    parts = frontmatter.split(state.read_bytes().decode("utf-8"))
    assert parts.body == body
    assert frontmatter.load_header(parts)["attempts"] == 1


def test_block_ids_grow_and_are_not_reused(home: Path) -> None:
    pages.create_space(home, "work")
    page = pages.create_page(home, "work", "p")
    assert pages.allocate_block(page) == "b01"
    (page / "log.md").write_text("<!-- b02 | 2026-09-24T08:00:00+09:00 | user | target=page -->\nhi\n")
    (page / "blocks" / "b04-x.json").write_text("{}")
    assert pages.allocate_block(page) == "b05"
    (page / "blocks" / "b04-x.json").unlink()
    assert pages.allocate_block(page) == "b06"
    pages.append_block(page, "b06")
    pages.append_block(page, "b06")
    assert frontmatter.read(page / "page.md")[0]["blocks"] == ["b06"]
    assert validate_target(page) == []


def test_block_files_skip_sidecars(home: Path) -> None:
    pages.create_space(home, "work")
    page = pages.create_page(home, "work", "p")
    blocks = page / "blocks"
    for name in ("b03-cv.json", "b03-cv.meta.yaml", "b30-other.md"):
        (blocks / name).write_text("x")
    assert [p.name for p in pages.block_files(page, "b03")] == ["b03-cv.json"]
    assert pages.block_files(page, "nope") == []
