import sys
from pathlib import Path

import pytest

from madang.config import RunnerSpec

FIXTURES = Path(__file__).parent / "fixtures"
STREAMS = FIXTURES / "streams"
FAKE_CLI = FIXTURES / "bin" / "fake_cli.py"


@pytest.fixture
def fake_spec() -> RunnerSpec:
    """Returns a runner spec that runs the fake CLI with templated args."""
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
