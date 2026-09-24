"""규칙 결정기: 접두, 키워드 표, 기본 종류로 요청 종류를 고른다."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from madang.config import RoutesConfig
from madang.deciders.base import Decider, DeciderChain, Decision, Question

NAME = "rules"
# 접두는 사용자가 종류를 직접 고른 것이다.
PREFIX_CONFIDENCE = 1.0
# 한 종류의 키워드만 맞았다.
KEYWORD_CONFIDENCE = 0.9
# 맞은 키워드가 없어 기본 종류를 쓴다. 기본 기준(0.7)은 통과한다.
DEFAULT_CONFIDENCE = 0.7
# 여러 종류의 키워드가 같은 수만큼 맞았다. 사람에게 묻는다.
TIE_CONFIDENCE = 0.4
ELEMENT_KIND = "small"
BLOCK_KIND = "build"

_PREFIX = re.compile(r"^\s*([A-Za-z_]+)\s*:")


class RulesDecider:
    """routes.yaml의 규칙만으로 요청 종류를 고르는 결정기.

    Attributes:
        routes: 라우팅 표.
    """

    def __init__(self, routes: RoutesConfig) -> None:
        self.routes = routes

    def decide(self, question: Question) -> Decision:
        """메시지 본문에서 요청 종류를 고른다.

        접두(``design: …``)가 있으면 그 종류, 없으면 키워드가 가장 많이
        맞은 종류, 아무것도 맞지 않으면 기본 종류다.

        Args:
            question: ``prompt``가 메시지 본문인 ``choice`` 질문.

        Returns:
            고른 종류와 확신도.
        """
        kinds = question.options or self.routes.kinds
        prefixed = self._prefix(question.prompt, kinds)
        if prefixed is not None:
            return Decision(prefixed, PREFIX_CONFIDENCE, NAME)
        scores = keyword_scores(question.prompt, self.routes.rules, kinds)
        if not scores:
            return Decision(self.routes.default_kind, DEFAULT_CONFIDENCE, NAME)
        best = max(scores.values())
        leaders = [kind for kind, score in scores.items() if score == best]
        confidence = KEYWORD_CONFIDENCE if len(leaders) == 1 else TIE_CONFIDENCE
        return Decision(leaders[0], confidence, NAME)

    def _prefix(self, text: str, kinds: list[str]) -> str | None:
        if not self.routes.prefix_override:
            return None
        match = _PREFIX.match(text)
        if match and match.group(1).lower() in kinds:
            return match.group(1).lower()
        return None


def keyword_scores(
    text: str, rules: Mapping[str, list[str]], kinds: list[str]
) -> dict[str, int]:
    """종류별로 본문에 나온 키워드 수를 센다.

    Args:
        text: 메시지 본문.
        rules: 종류별 키워드.
        kinds: 셀 종류. 표의 순서를 따른다.

    Returns:
        하나 이상 맞은 종류만 담은 점수. ``rules`` 순서를 유지한다.
    """
    lowered = text.lower()
    scores = {
        kind: sum(1 for word in words if word.lower() in lowered)
        for kind, words in rules.items()
        if kind in kinds
    }
    return {kind: score for kind, score in scores.items() if score}


def target_kind(target: Mapping[str, Any]) -> str | None:
    """대상이 블록이면 고정 종류를 반환한다.

    Args:
        target: ``{block, elements, mode}``.

    Returns:
        요소를 골랐으면 ``small``, 블록만 골랐으면 ``build``, 페이지
        대상이면 None.
    """
    if not target.get("block"):
        return None
    return ELEMENT_KIND if target.get("elements") else BLOCK_KIND


def build_chain(routes: RoutesConfig) -> DeciderChain:
    """routes.yaml의 ``decider.chain`` 중 구현된 결정기로 체인을 만든다.

    아직 없는 결정기(예: ``light_model``)는 건너뛴다.

    Args:
        routes: 라우팅 표.

    Returns:
        결정기 체인.
    """
    known: dict[str, Decider] = {NAME: RulesDecider(routes)}
    deciders = [known[name] for name in routes.decider.chain if name in known]
    return DeciderChain(deciders, routes.decider.min_confidence)
