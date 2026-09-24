from pathlib import Path

import pytest

from madang import config
from madang.policy import (
    NO_TEST_COMMAND,
    TESTS_NOT_RUN,
    MergeCheck,
    Policy,
    denied,
    runner_args,
)


def policy(**auto_merge) -> Policy:
    return Policy(
        config.ProjectPolicy(auto_merge=config.AutoMerge(**auto_merge))
    )


def test_default_deny_list() -> None:
    assert config.ProjectConfig().policy.deny == [
        "push --force",
        "reset --hard",
        "clean -fd",
    ]


def test_auto_merge_without_declared_test_is_refused() -> None:
    decision = policy().can_auto_merge(MergeCheck(test_exit=0))
    assert not decision.allowed
    assert decision.reasons == [NO_TEST_COMMAND]


@pytest.mark.parametrize(
    ("check", "reasons"),
    [
        (MergeCheck(test_exit=0), []),
        (MergeCheck(), [TESTS_NOT_RUN]),
        (MergeCheck(test_exit=2), ["테스트 실패(종료 코드 2)"]),
        (MergeCheck(test_exit=0, conflicts=["a.py"]), ["충돌: a.py"]),
    ],
)
def test_auto_merge_needs_passing_tests_and_no_conflict(
    check: MergeCheck, reasons: list[str]
) -> None:
    decision = policy(test="uv run pytest").can_auto_merge(check)
    assert decision.reasons == reasons
    assert decision.allowed is (not reasons)


def test_auto_merge_rules_can_be_turned_off() -> None:
    loose = policy(require_tests=False, require_no_conflict=False)
    assert loose.can_auto_merge(MergeCheck(conflicts=["a.py"])).allowed


def test_auto_publish_needs_switch_and_target() -> None:
    assert policy().can_auto_publish().reasons == [
        "자동 게시가 꺼져 있다",
        "게시 대상 없음",
    ]
    on = Policy(
        config.ProjectPolicy(auto_publish=True),
        config.PublishSettings(target="gh-pages"),
    )
    assert on.can_auto_publish().allowed


@pytest.mark.parametrize(
    "command",
    [
        "git push --force",
        "git push origin main --force",
        "git push -f origin main",
        "git push origin +main",
        "git -C /tmp/x push --force",
        "cd app && git reset --hard HEAD~1",
        "GIT_DIR=.git git clean -fd",
        "git clean -df",
        "git clean -f -d -x",
        ["git", "reset", "--hard"],
    ],
)
def test_check_deny_blocks_default_rules(command) -> None:
    decision = Policy().check_deny(command)
    assert not decision.allowed
    assert decision.reasons[0].startswith("금지 명령: ")


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git push --force-with-lease",
        "git reset --soft HEAD~1",
        "git clean -n",
        "git commit -m 'push --force'",
        "echo git push --force",
        "ls -fd",
    ],
)
def test_check_deny_allows_other_commands(command: str) -> None:
    assert Policy().check_deny(command).allowed


def test_deny_uses_project_config(tmp_path: Path) -> None:
    path = tmp_path / ".madang" / "config.yaml"
    path.parent.mkdir()
    path.write_text(
        'policy:\n  deny: ["checkout ."]\n  auto_merge: {test: "make test"}\n'
    )
    loaded = Policy.load(tmp_path)
    assert loaded.test_command == "make test"
    assert not loaded.check_deny("git checkout .").allowed
    assert loaded.check_deny("git reset --hard").allowed


def test_denied_returns_matching_rule() -> None:
    assert denied("git reset --hard", ["push --force", "reset --hard"]) == (
        "reset --hard"
    )


def test_runner_args_for_claude_disallow_bash_patterns() -> None:
    args = runner_args("claude", ["push --force", "reset --hard"])
    assert args == [
        "--disallowedTools",
        "Bash(git push --force)",
        "Bash(git push --force *)",
        "Bash(git reset --hard)",
        "Bash(git reset --hard *)",
    ]
    assert Policy().runner_args("claude")[0] == "--disallowedTools"


def test_runner_args_empty_without_rules_or_support() -> None:
    assert runner_args("claude", []) == []
    assert runner_args("codex", ["push --force"]) == []
