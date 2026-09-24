"""앱 홈 저장소들이 함께 쓰는 파일 도우미."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    """임시 파일을 거쳐 ``path``를 ``text``로 교체한다.

    Args:
        path: 쓸 파일.
        text: 새 내용. 줄바꿈 변환 없이 UTF-8로 쓴다.
    """
    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
