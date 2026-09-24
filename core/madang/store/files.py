"""앱 홈 저장소들이 함께 쓰는 파일 도우미."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, text: str | bytes) -> None:
    """임시 파일을 거쳐 ``path``를 ``text``로 교체한다.

    Args:
        path: 쓸 파일.
        text: 새 내용. 문자열은 줄바꿈 변환 없이 UTF-8로, 바이트는 그대로
            쓴다.
    """
    data = text.encode("utf-8") if isinstance(text, str) else text
    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
