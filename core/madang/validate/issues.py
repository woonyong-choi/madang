"""검사기들이 함께 쓰는 검사 문제 타입과 YAML 줄 번호 조회."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Issue:
    """검사에서 찾은 문제 하나.

    Attributes:
        code: 짧은 kebab-case 식별자. 예: ``missing-key``.
        message: 무엇이 잘못됐는지.
        line: 1부터 시작하는 파일 줄 번호(알 수 있을 때).
        path: 파일(알 수 있을 때).
    """

    code: str
    message: str
    line: int | None = None
    path: Path | None = None

    def format(self) -> str:
        """터미널 출력용 ``path:line: code message``를 반환한다."""
        where = str(self.path) if self.path is not None else "-"
        if self.line is not None:
            where = f"{where}:{self.line}"
        return f"{where}: {self.code} {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """문제를 JSON으로 바꿀 수 있는 dict로 반환한다."""
        data = asdict(self)
        data["path"] = str(self.path) if self.path is not None else None
        return data


class Lines:
    """YAML 머리부 노드의 파일 줄 번호.

    ``offset``은 머리부 첫 줄의 1부터 시작하는 파일 줄 번호이다.
    """

    def __init__(self, header: str | None, offset: int) -> None:
        self.offset = offset
        self.root: yaml.Node | None = None
        if header:
            try:
                self.root = yaml.compose(header, Loader=yaml.SafeLoader)
            except yaml.YAMLError:
                self.root = None

    def _line(self, node: yaml.Node) -> int:
        return self.offset + node.start_mark.line

    def key(self, *path: str | int) -> int | None:
        """``path``에 있는 키나 항목의 파일 줄 번호를 반환한다.

        Args:
            *path: 루트에서부터의 매핑 키와 시퀀스 인덱스.

        Returns:
            ``path``에서 찾은 가장 깊은 노드의 줄. 첫 부분조차 찾지 못하면
            None.
        """
        node = self.root
        line = None
        for part in path:
            found = None
            if isinstance(node, yaml.MappingNode):
                found = next(
                    (
                        (k, v)
                        for k, v in node.value
                        if isinstance(k, yaml.ScalarNode) and k.value == part
                    ),
                    None,
                )
            elif (
                isinstance(node, yaml.SequenceNode)
                and isinstance(part, int)
                and 0 <= part < len(node.value)
            ):
                found = (node.value[part], node.value[part])
            if found is None:
                return line
            line, node = self._line(found[0]), found[1]
        return line
