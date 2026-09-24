import sys
from pathlib import Path

import pytest

from madang.config import RunnerSpec

FIXTURES = Path(__file__).parent / "fixtures"
STREAMS = FIXTURES / "streams"
FAKE_CLI = FIXTURES / "bin" / "fake_cli.py"


@pytest.fixture
def fake_spec() -> RunnerSpec:
    """템플릿 인자로 가짜 CLI를 실행하는 러너 스펙을 반환한다."""
    return RunnerSpec(
        bin=sys.executable,
        args=[
            str(FAKE_CLI),
            "--model",
            "{model}",
            "--effort",
            "{effort}",
            "--add-dir",
            "{home}",
        ],
    )
