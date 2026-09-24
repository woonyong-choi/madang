from pathlib import Path

import pytest

from madang.store import frontmatter
from madang.store.page import load_page

FIXTURES = Path(__file__).parent / "fixtures" / "state"


@pytest.mark.parametrize(
    "text",
    [
        "---\na: 1\n---\n## 목표\n본문\n",
        "---\r\na: 1\r\n---\r\nbody\r\n",
        "---\na: 1\n---",
        "---\n---\nbody without header keys\n",
        "no front matter\n---\nstill body\n",
        "",
    ],
)
def test_split_join_round_trip(text: str) -> None:
    assert frontmatter.join(frontmatter.split(text)) == text


def test_round_trip_fixture_files() -> None:
    for path in FIXTURES.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert frontmatter.join(frontmatter.split(text)) == text, path


def test_parse_header_and_body() -> None:
    header, body = frontmatter.parse(
        "---\nstatus: doing\ntags: [a, b]\n---\n## 목표\n"
    )
    assert header == {"status": "doing", "tags": ["a", "b"]}
    assert body == "## 목표\n"


def test_body_line() -> None:
    parts = frontmatter.split("---\na: 1\nb: 2\n---\nbody\n")
    assert parts.header_line == 2
    assert parts.body_line == 5


def test_unclosed_header_raises() -> None:
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.split("---\na: 1\nbody\n")


def test_non_mapping_header_raises() -> None:
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\n- a\n- b\n---\n")


def test_invalid_yaml_reports_line() -> None:
    with pytest.raises(frontmatter.FrontmatterError) as err:
        frontmatter.parse("---\na: 1\nb: [\n---\n")
    assert err.value.line is not None and err.value.line >= 2


def test_dumps_keeps_body_and_order() -> None:
    text = frontmatter.dumps(
        {"status": "doing", "kind": "build"}, "## 목표\n본문\n"
    )
    assert text == "---\nstatus: doing\nkind: build\n---\n## 목표\n본문\n"
    assert frontmatter.parse(text) == (
        {"status": "doing", "kind": "build"},
        "## 목표\n본문\n",
    )


def test_load_page_model() -> None:
    page, body = load_page(FIXTURES / "valid-1")
    assert page.id == "2026-09-24-resume"
    assert page.status == "doing"
    assert page.blocks == ["b01", "b05"]
    assert page.tags == ["지원"]
    assert body.startswith("이력서")
