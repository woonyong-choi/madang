"""결정기 인터페이스와 확신도 기준으로 결정기를 잇는 체인."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class Question:
    """결정기에 묻는 질문 하나.

    Attributes:
        kind: 답의 형태.
        prompt: 판단할 텍스트. 요청 종류라면 메시지 본문.
        options: ``choice``의 선택지.
        state: 관련 상태 텍스트. 짧게.
        page_kind: 요청을 받은 페이지의 종류(page.md ``kind``). 규칙이 맞지
            않을 때 기본 작업 종류를 고르는 데 쓴다.
    """

    kind: Literal["choice", "yesno", "score"]
    prompt: str
    options: list[str] | None = None
    state: str = ""
    page_kind: str | None = None


@dataclass
class Decision:
    """결정기의 답.

    Attributes:
        choice: 고른 값.
        confidence: 0~1 확신도.
        by: 답한 결정기 이름.
    """

    choice: str | bool | int
    confidence: float
    by: str


class Decider(Protocol):
    """질문 하나에 답하는 것."""

    def decide(self, question: Question) -> Decision:
        """질문에 답한다."""
        ...


class DeciderChain:
    """앞 결정기의 확신도가 모자라면 다음 결정기에 묻는다.

    Attributes:
        deciders: 묻는 순서대로 나열한 결정기.
        min_confidence: 답으로 받아들이는 최소 확신도.
    """

    def __init__(
        self, deciders: Sequence[Decider], min_confidence: float
    ) -> None:
        self.deciders = list(deciders)
        self.min_confidence = min_confidence

    def decide(self, question: Question) -> Decision | None:
        """확신도를 넘는 첫 답을 반환한다.

        Args:
            question: 질문.

        Returns:
            받아들인 답. 모든 결정기가 기준 미만이면 None이며, 이때는
            사람에게 묻는다.
        """
        for decider in self.deciders:
            decision = decider.decide(question)
            if decision.confidence >= self.min_confidence:
                return decision
        return None
