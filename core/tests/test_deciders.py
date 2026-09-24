import pytest

from madang.config import RoutesConfig, load_config
from madang.deciders import (
    DeciderChain,
    Decision,
    Question,
    RulesDecider,
    build_chain,
    target_kind,
)


@pytest.fixture
def routes(tmp_path) -> RoutesConfig:
    return load_config(tmp_path).routes


def ask(text: str) -> Question:
    return Question(kind="choice", prompt=text)


def test_prefix_overrides_keywords(routes: RoutesConfig) -> None:
    decision = RulesDecider(routes).decide(ask("review: 설계 문서 오타"))
    assert decision == Decision("review", 1.0, "rules")


def test_unknown_prefix_is_ignored(routes: RoutesConfig) -> None:
    decision = RulesDecider(routes).decide(ask("note: 구조를 바꿔줘"))
    assert decision.choice == "design"


def test_prefix_can_be_disabled(routes: RoutesConfig) -> None:
    routes.prefix_override = False
    decision = RulesDecider(routes).decide(ask("small: 아키텍처 정리"))
    assert decision.choice == "design"


def test_single_keyword_kind(routes: RoutesConfig) -> None:
    decision = RulesDecider(routes).decide(ask("이 함수 어디 있는지 찾아줘"))
    assert decision.choice == "explore" and decision.confidence >= 0.7


def test_default_kind_when_nothing_matches(routes: RoutesConfig) -> None:
    decision = RulesDecider(routes).decide(ask("로그인 화면을 만들어줘"))
    assert decision.choice == "build"
    assert decision.confidence == routes.decider.min_confidence


def test_tie_falls_below_confidence(routes: RoutesConfig) -> None:
    question = ask("구조를 검토해줘")
    decision = RulesDecider(routes).decide(question)
    assert decision.confidence < routes.decider.min_confidence
    assert build_chain(routes).decide(question) is None


def test_chain_skips_missing_deciders(routes: RoutesConfig) -> None:
    chain = build_chain(routes)
    assert [type(d).__name__ for d in chain.deciders] == ["RulesDecider"]
    assert chain.decide(ask("설계해줘")).choice == "design"


def test_chain_moves_to_next_decider() -> None:
    class Fixed:
        def __init__(self, choice, confidence):
            self.answer = Decision(choice, confidence, "fixed")

        def decide(self, question):
            return self.answer

    chain = DeciderChain([Fixed("a", 0.2), Fixed("b", 0.8)], 0.7)
    assert chain.decide(ask("x")).choice == "b"
    assert DeciderChain([Fixed("a", 0.2)], 0.7).decide(ask("x")) is None


def test_block_target_fixes_kind() -> None:
    assert target_kind({"block": None}) is None
    assert target_kind({"block": "b04"}) == "build"
    assert target_kind({"block": "b04", "elements": ["work[1]"]}) == "small"
