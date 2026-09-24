"""정책: 프로젝트 ``config.yaml``의 ``policy``로 부작용을 허락할지 판단한다.

판단은 사실과 선언만 쓴다. 자동 머지는 선언된 ``test`` 명령의 결과와
충돌 여부, 자동 게시는 ``auto_publish``와 선언된 게시 대상, 금지 명령은
``deny`` 목록으로 정한다. 거부하면 사람이 읽을 사유를 함께 돌려준다.
에이전트가 받는 공통 부작용 규칙(``AGENT_RULES``)도 여기 둔다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from madang import config
from madang.policy.agent import AGENT_RULES, with_rules
from madang.policy.deny import denied, runner_args

NO_TEST_COMMAND = "테스트 명령 없음"
TESTS_NOT_RUN = "테스트를 실행하지 않았다"
AUTO_PUBLISH_OFF = "자동 게시가 꺼져 있다"
NO_PUBLISH_TARGET = "게시 대상 없음"


@dataclass(frozen=True)
class Decision:
    """정책 판단 하나.

    Attributes:
        allowed: 허락하면 참.
        reasons: 거부 사유. 허락이면 빈 목록.
    """

    allowed: bool
    reasons: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, reasons: list[str]) -> Decision:
        """사유가 없으면 허락, 있으면 거부."""
        return cls(allowed=not reasons, reasons=reasons)


@dataclass(frozen=True)
class MergeCheck:
    """자동 머지 판단에 쓰는 관찰 결과.

    Attributes:
        test_exit: 선언된 ``test`` 명령의 종료 코드. 실행하지 않았으면 None.
        conflicts: 머지하면 충돌할 파일.
        approved: 사람이 묻는 블록에서 테스트 조건 없이 머지하라고 답했으면
            참. 충돌 조건은 넘기지 못한다.
    """

    test_exit: int | None = None
    conflicts: Sequence[str] = ()
    approved: bool = False


def conflict_reason(paths: Sequence[str]) -> str:
    """머지 충돌 파일을 사람이 읽을 거부 사유로 바꾼다."""
    return "충돌: " + ", ".join(paths)


class Policy:
    """프로젝트 하나의 정책.

    Attributes:
        settings: ``config.yaml``의 ``policy``.
        publish: ``config.yaml``의 ``publish``.
    """

    def __init__(
        self,
        settings: config.ProjectPolicy | None = None,
        publish: config.PublishSettings | None = None,
    ) -> None:
        self.settings = settings or config.ProjectPolicy()
        self.publish = publish or config.PublishSettings()

    @classmethod
    def load(cls, root: Path) -> Policy:
        """``<root>/.madang/config.yaml``에서 정책을 읽는다.

        Raises:
            OSError: 설정 파일을 읽을 수 없다.
            ConfigError: 설정이 올바르지 않다.
        """
        project = config.load_project_config(root)
        return cls(project.policy, project.publish)

    @property
    def test_command(self) -> str | None:
        """자동 머지 전에 돌릴 선언된 테스트 명령."""
        return self.settings.auto_merge.test

    def can_auto_merge(self, result: MergeCheck) -> Decision:
        """관찰 결과가 자동 머지 조건을 채우는지 판단한다.

        Args:
            result: 테스트 종료 코드와 충돌 파일.

        Returns:
            판단. ``require_tests``인데 ``test`` 선언이 없으면
            "테스트 명령 없음"으로 거부한다. 사람이 승인했으면 테스트
            조건은 보지 않는다.
        """
        rules = self.settings.auto_merge
        reasons = []
        if rules.require_tests and not result.approved:
            if not self.test_command:
                reasons.append(NO_TEST_COMMAND)
            elif result.test_exit is None:
                reasons.append(TESTS_NOT_RUN)
            elif result.test_exit != 0:
                reasons.append(f"테스트 실패(종료 코드 {result.test_exit})")
        if rules.require_no_conflict and result.conflicts:
            reasons.append(conflict_reason(result.conflicts))
        return Decision.of(reasons)

    def can_auto_publish(self) -> Decision:
        """자동 게시가 켜져 있고 게시 대상이 선언됐는지 판단한다."""
        reasons = []
        if not self.settings.auto_publish:
            reasons.append(AUTO_PUBLISH_OFF)
        if not self.publish.target:
            reasons.append(NO_PUBLISH_TARGET)
        return Decision.of(reasons)

    def check_deny(self, command: str | Sequence[str]) -> Decision:
        """명령이 ``deny`` 목록에 걸리는지 판단한다.

        Args:
            command: 셸 명령줄 또는 인자 목록.

        Returns:
            걸리면 그 항목을 사유로 한 거부.
        """
        rule = denied(command, self.settings.deny)
        return Decision.of([] if rule is None else [f"금지 명령: {rule}"])

    def runner_args(self, runner: str) -> list[str]:
        """러너가 ``deny`` 목록을 막도록 명령줄에 더할 인자."""
        return runner_args(runner, self.settings.deny)


__all__ = [
    "AGENT_RULES",
    "AUTO_PUBLISH_OFF",
    "NO_PUBLISH_TARGET",
    "NO_TEST_COMMAND",
    "TESTS_NOT_RUN",
    "Decision",
    "MergeCheck",
    "Policy",
    "conflict_reason",
    "denied",
    "runner_args",
    "with_rules",
]
