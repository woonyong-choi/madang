"""금지 명령: ``policy.deny``의 git 명령과 맞는지 판단하고 러너 인자로 옮긴다.

금지 항목은 ``"push --force"``처럼 git 하위 명령과 그 옵션이다. 명령줄의
git 호출이 같은 하위 명령을 쓰고 항목의 옵션을 모두 가지면 금지다. 짧은
옵션 묶음(``-fd``)은 낱개로 풀고, git에서 ``-f``는 ``--force``와 같다.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable, Sequence

GIT = "git"
# 값을 하나 받는 git 전역 옵션.
_GLOBAL_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree"})
# 셸에서 명령을 나누는 기호.
_SEPARATORS = frozenset({";", "&&", "||", "|", "&", "(", ")"})
# git에서 뜻이 같은 옵션 -> 대표 이름.
_SYNONYMS = {"-f": "--force"}
# claude는 금지 도구를 이 옵션으로 받는다(`claude --help`로 확인한 사실).
CLAUDE_DISALLOWED = "--disallowedTools"


def denied(command: str | Sequence[str], deny: Iterable[str]) -> str | None:
    """``command``가 ``deny`` 항목과 맞으면 그 항목을, 아니면 None을 반환한다.

    Args:
        command: 셸 명령줄 문자열 또는 인자 목록.
        deny: ``"push --force"`` 형식의 금지 항목.

    Returns:
        처음 맞은 금지 항목.
    """
    rules = [(rule, _parse_rule(rule)) for rule in deny]
    for call in _git_calls(command):
        for rule, (sub, options) in rules:
            if call[0] == sub and options <= call[1]:
                return rule
    return None


def runner_args(runner: str, deny: Iterable[str]) -> list[str]:
    """러너 명령줄에 붙여 금지 항목을 막게 하는 인자를 반환한다.

    claude는 ``--disallowedTools``에 ``Bash(<명령> *)`` 규칙을 받는다. 이
    옵션은 값을 여러 개 받으므로 뒤에 다른 옵션이나 ``--``가 와야 한다.
    codex exec에는 금지 명령을 받는 명령줄 옵션이 없어 빈 목록이다.

    Args:
        runner: 러너 이름(``claude``, ``codex``).
        deny: 금지 항목.

    Returns:
        명령줄에 더할 인자.
    """
    rules = [rule.strip() for rule in deny if rule.strip()]
    if runner != "claude" or not rules:
        return []
    tools = []
    for rule in rules:
        tools += [f"Bash({GIT} {rule})", f"Bash({GIT} {rule} *)"]
    return [CLAUDE_DISALLOWED, *tools]


def _parse_rule(rule: str) -> tuple[str, frozenset[str]]:
    words = shlex.split(rule)
    if words and words[0] == GIT:
        words = words[1:]
    if not words:
        raise ValueError(f"empty deny rule: {rule!r}")
    return words[0], _options(words[1:], words[0])


def _git_calls(
    command: str | Sequence[str],
) -> list[tuple[str, frozenset[str]]]:
    """명령줄 안의 git 호출을 ``(하위 명령, 옵션 집합)``으로 낸다."""
    words = _tokens(command) if isinstance(command, str) else list(command)
    calls = []
    segment: list[str] = []
    for word in [*words, ";"]:
        if word not in _SEPARATORS:
            segment.append(word)
            continue
        call = _git_call(segment)
        if call is not None:
            calls.append(call)
        segment = []
    return calls


def _tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        # 따옴표가 닫히지 않은 명령은 공백으로만 나눈다.
        return command.split()


def _git_call(words: list[str]) -> tuple[str, frozenset[str]] | None:
    # 앞의 환경 변수 대입(FOO=1 git ...)은 건너뛴다.
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    if not words or words[0].rsplit("/", 1)[-1] != GIT:
        return None
    rest = iter(words[1:])
    for word in rest:
        if word in _GLOBAL_WITH_VALUE:
            next(rest, None)
        elif not word.startswith("-"):
            return word, _options(list(rest), word)
    return None


def _options(words: list[str], sub: str) -> frozenset[str]:
    found: set[str] = set()
    for word in words:
        if word.startswith("--"):
            found.add(word.split("=", 1)[0])
        elif word.startswith("-") and len(word) > 1:
            found.update(f"-{letter}" for letter in word[1:])
        elif sub == "push" and word.startswith("+"):
            found.add("--force")  # +refspec는 그 참조만 강제로 푼다
    return frozenset(_SYNONYMS.get(option, option) for option in found)
