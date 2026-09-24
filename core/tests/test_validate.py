import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from madang.cli import app
from madang.validate import validate_page, validate_state, validate_target

FIXTURES = Path(__file__).parent / "fixtures" / "state"
runner = CliRunner()

STATE = """---
status: doing
kind: build
tier: 1
attempts: 0
artifacts:
{artifacts}
---
## 목표
목표.

## 다음 할 일
할 일.
"""


def codes(issues) -> set[str]:
    return {issue.code for issue in issues}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "madang-home"
    monkeypatch.setenv("MADANG_HOME", str(home))
    return home


@pytest.mark.parametrize("name", ["valid-1", "valid-2", "valid-3"])
def test_valid_fixtures(name: str) -> None:
    assert validate_target(FIXTURES / name) == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("invalid-1", {"missing-key"}),
        ("invalid-2", {"token-limit"}),
        ("invalid-3", {"artifact-missing"}),
        ("invalid-4", {"done-without-verify"}),
        ("invalid-5", {"duplicate-decision", "choice-not-in-options", "invalid-value"}),
        ("invalid-6", {"invalid-value", "missing-section"}),
    ],
)
def test_invalid_fixtures(name: str, expected: set[str]) -> None:
    assert codes(validate_target(FIXTURES / name)) == expected


def test_issue_lines_point_at_keys() -> None:
    issues = validate_target(FIXTURES / "invalid-5")
    by_code = {issue.code: issue.line for issue in issues}
    assert by_code == {"duplicate-decision": 12, "choice-not-in-options": 14, "invalid-value": 16}
    artifact = validate_target(FIXTURES / "invalid-3")[0]
    assert artifact.line == 8
    assert artifact.path == FIXTURES / "invalid-3" / "state.md"


def test_state_file_is_not_modified() -> None:
    path = FIXTURES / "invalid-6" / "state.md"
    before = path.read_bytes()
    validate_state(path)
    assert path.read_bytes() == before


def test_token_limit_is_configurable() -> None:
    path = FIXTURES / "valid-1" / "state.md"
    assert "token-limit" in codes(validate_state(path, token_limit=50))
    assert validate_state(FIXTURES / "invalid-2" / "state.md", token_limit=100_000) == []


def test_missing_front_matter(tmp_path: Path) -> None:
    path = tmp_path / "state.md"
    path.write_text("## 목표\n\n## 다음 할 일\n", encoding="utf-8")
    issues = validate_state(path)
    assert "frontmatter" in codes(issues)
    assert "missing-key" in codes(issues)


def test_missing_state_file(tmp_path: Path) -> None:
    assert codes(validate_target(tmp_path)) == {"missing-file"}


def test_done_uses_highest_numbered_run(tmp_path: Path) -> None:
    (tmp_path / "runs").mkdir()
    (tmp_path / "state.md").write_text(
        STATE.replace("status: doing", "status: done").format(artifacts="  []"), encoding="utf-8"
    )
    (tmp_path / "runs" / "9.json").write_text(json.dumps({"verify": {"ok": True}}))
    (tmp_path / "runs" / "10.json").write_text(json.dumps({"verify": {"ok": False}}))
    assert codes(validate_target(tmp_path)) == {"done-without-verify"}
    (tmp_path / "runs" / "11.json").write_text(json.dumps({"verify": {"ok": True}}))
    assert validate_target(tmp_path) == []
    (tmp_path / "runs" / "12.json").write_text("{not json")
    assert codes(validate_target(tmp_path)) == {"done-without-verify"}


def make_space(tmp_path: Path, repo: str) -> Path:
    space = tmp_path / "spaces" / "work"
    page = space / "pages" / "2026-09-24-lock"
    (page / "blocks").mkdir(parents=True)
    (space / "space.md").write_text(f"---\nslug: work\ntitle: Work\nrepo: {repo}\n---\n", encoding="utf-8")
    (page / "blocks" / "b05-race.md").write_text("분석\n", encoding="utf-8")
    (page / "state.md").write_text(
        STATE.format(artifacts="  - blocks/b05-race.md\n  - repo:src/lock.ts"), encoding="utf-8"
    )
    return page


def test_repo_artifact_resolved_from_space(tmp_path: Path) -> None:
    code = tmp_path / "code"
    (code / "src").mkdir(parents=True)
    (code / "src" / "lock.ts").write_text("export {}\n")
    page = make_space(tmp_path, str(code))
    assert validate_target(page) == []
    assert validate_target(page / "state.md") == []


def test_repo_relative_to_space(tmp_path: Path) -> None:
    page = make_space(tmp_path, "../../code")
    code = tmp_path / "code"
    (code / "src").mkdir(parents=True)
    (code / "src" / "lock.ts").write_text("export {}\n")
    assert validate_target(page) == []


def test_repo_artifact_missing_in_repo(tmp_path: Path) -> None:
    (tmp_path / "code").mkdir()
    page = make_space(tmp_path, str(tmp_path / "code"))
    assert codes(validate_target(page)) == {"artifact-missing"}


def test_repo_artifact_without_repo(tmp_path: Path) -> None:
    page = make_space(tmp_path, "null")
    assert codes(validate_target(page)) == {"repo-unset"}


def test_repo_override(tmp_path: Path) -> None:
    page = make_space(tmp_path, "null")
    other = tmp_path / "other"
    (other / "src").mkdir(parents=True)
    (other / "src" / "lock.ts").write_text("export {}\n")
    assert validate_target(page, repo=other) == []


def test_artifact_escaping_folder(tmp_path: Path) -> None:
    (tmp_path / "state.md").write_text(
        STATE.format(artifacts="  - ../outside.md\n  - /etc/hosts"), encoding="utf-8"
    )
    issues = validate_target(tmp_path)
    assert [issue.code for issue in issues] == ["invalid-artifact", "invalid-artifact"]


def test_invalid_page_md(tmp_path: Path) -> None:
    path = tmp_path / "page.md"
    path.write_text("---\ntitle: x\nstatus: finished\n---\n", encoding="utf-8")
    issues = validate_page(path)
    assert codes(issues) == {"missing-key", "invalid-value"}
    assert {issue.line for issue in issues} == {2, 3}


def test_cli_valid_exit_zero() -> None:
    result = runner.invoke(app, ["validate", str(FIXTURES / "valid-1")])
    assert result.exit_code == 0, result.output
    assert result.output == ""


def test_cli_invalid_prints_file_line_code() -> None:
    result = runner.invoke(app, ["validate", str(FIXTURES / "invalid-1" / "state.md")])
    assert result.exit_code == 1
    path = FIXTURES / "invalid-1" / "state.md"
    assert result.output.startswith(f"{path}:2: missing-key ")


def test_cli_json() -> None:
    result = runner.invoke(app, ["validate", "--json", str(FIXTURES / "invalid-4")])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert [issue["code"] for issue in data["issues"]] == ["done-without-verify"]
    ok = runner.invoke(app, ["validate", "--json", str(FIXTURES / "valid-2")])
    assert ok.exit_code == 0
    assert json.loads(ok.output) == {"ok": True, "issues": []}


def test_cli_uses_home_token_limit(isolated_home: Path) -> None:
    (isolated_home / "config").mkdir(parents=True)
    (isolated_home / "config" / "madang.yaml").write_text("limits:\n  state_tokens: 50\n")
    result = runner.invoke(app, ["validate", str(FIXTURES / "valid-1")])
    assert result.exit_code == 1
    assert "token-limit" in result.output


def test_cli_repo_option(tmp_path: Path) -> None:
    page = make_space(tmp_path, "null")
    other = tmp_path / "other"
    (other / "src").mkdir(parents=True)
    (other / "src" / "lock.ts").write_text("export {}\n")
    assert runner.invoke(app, ["validate", str(page)]).exit_code == 1
    assert runner.invoke(app, ["validate", str(page), "--repo", str(other)]).exit_code == 0


def test_cli_missing_target(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "nope")])
    assert result.exit_code == 2
