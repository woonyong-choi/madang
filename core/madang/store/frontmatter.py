"""YAML 머리부: 마크다운 파일을 머리부와 본문으로 나누고 다시 합친다.

``split`` 다음 ``join``은 원문을 바이트 단위로 그대로 돌려주므로,
호출자는 본문을 건드리지 않고 머리부를 읽을 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FENCE = "---"


class FrontmatterError(ValueError):
    """나누거나 파싱할 수 없는 머리부.

    Attributes:
        line: 문제가 있는 파일의 1부터 시작하는 줄 번호(알 수 있을 때).
    """

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


@dataclass
class Parts:
    """머리부 울타리에서 잘라 낸 파일.

    ``header``는 울타리 사이의 원본 YAML이다(머리부가 없으면 ``None``).
    ``open_nl``/``close_nl``은 울타리 줄의 줄바꿈을 보존해 ``join``이
    손실 없이 동작하게 한다.
    """

    header: str | None
    body: str
    open_nl: str = "\n"
    close_nl: str = "\n"

    @property
    def header_line(self) -> int:
        """머리부 첫 줄의 1부터 시작하는 파일 줄 번호."""
        return 2

    @property
    def body_line(self) -> int:
        """본문이 시작하는 1부터 시작하는 파일 줄 번호."""
        if self.header is None:
            return 1
        return self.header.count("\n") + 3


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def split(text: str) -> Parts:
    """파일을 머리부 울타리에서 자른다.

    Args:
        text: 파일 내용.

    Returns:
        나눈 조각. 텍스트가 ``---``로 시작하지 않으면 ``header``는 None.

    Raises:
        FrontmatterError: 머리부가 닫히지 않았다.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != FENCE:
        return Parts(header=None, body=text)
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == FENCE:
            return Parts(
                header="".join(lines[1:i]),
                body="".join(lines[i + 1 :]),
                open_nl=_line_ending(lines[0]),
                close_nl=_line_ending(lines[i]),
            )
    raise FrontmatterError("front matter is not closed with '---'", line=1)


def join(parts: Parts) -> str:
    """``parts``의 파일 텍스트를 반환한다. ``split``의 역연산이다."""
    if parts.header is None:
        return parts.body
    return (
        f"{FENCE}{parts.open_nl}{parts.header}"
        f"{FENCE}{parts.close_nl}{parts.body}"
    )


def load_header(parts: Parts) -> dict[str, Any]:
    """머리부를 YAML 매핑으로 파싱한다.

    Args:
        parts: 나눈 파일.

    Returns:
        머리부 매핑. 머리부가 없으면 빈 dict.

    Raises:
        FrontmatterError: 머리부가 올바른 YAML이 아니거나 매핑이 아니다.
    """
    if parts.header is None:
        return {}
    try:
        data = yaml.safe_load(parts.header)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (
            parts.header_line + mark.line
            if mark is not None
            else parts.header_line
        )
        raise FrontmatterError(f"invalid YAML: {exc}", line=line) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FrontmatterError(
            "front matter must be a mapping", line=parts.header_line
        )
    return data


def parse(text: str) -> tuple[dict[str, Any], str]:
    """파일을 머리부 매핑과 본문으로 파싱한다.

    Args:
        text: 파일 내용.

    Returns:
        ``(header, body)`` 튜플.

    Raises:
        FrontmatterError: 머리부를 나누거나 파싱할 수 없다.
    """
    parts = split(text)
    return load_header(parts), parts.body


def read(path: Path) -> tuple[dict[str, Any], str]:
    """파일을 읽어 ``parse``처럼 파싱한다."""
    return parse(path.read_text(encoding="utf-8"))


def dump_header(header: dict[str, Any]) -> str:
    """머리부 매핑을 울타리 사이에 들어갈 YAML 텍스트로 반환한다."""
    return yaml.safe_dump(header, sort_keys=False, allow_unicode=True)


def dumps(header: dict[str, Any], body: str) -> str:
    """머리부 매핑과 본문으로 새 파일 텍스트를 만들어 반환한다."""
    return join(Parts(header=dump_header(header), body=body))
