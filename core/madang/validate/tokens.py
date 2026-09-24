"""토큰 추정: 상태 검사와 입력 조립이 함께 쓰는 계수기.

tiktoken ``cl100k_base``로 센다. 인코딩 파일을 쓸 수 없으면(오프라인 첫
실행) UTF-8 3바이트당 토큰 1개라는 보수적 추정으로 대신한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

TOKENIZER = "cl100k_base"
FALLBACK_TOKENIZER = "utf8-bytes/3"


@lru_cache(maxsize=1)
def _encoding() -> Any:
    try:
        import tiktoken

        return tiktoken.get_encoding(TOKENIZER)
    except Exception:  # 인코딩 파일을 쓸 수 없음(오프라인 첫 실행)
        return None


def uses_fallback() -> bool:
    """바이트 추정으로 세고 있는지(tiktoken을 못 쓰는지) 반환한다."""
    return _encoding() is None


def tokenizer_name() -> str:
    """쓰고 있는 계수기 이름(``cl100k_base`` 또는 바이트 추정)을 반환한다."""
    return FALLBACK_TOKENIZER if uses_fallback() else TOKENIZER


def count_tokens(text: str) -> int:
    """``text``의 토큰 수를 센다.

    Args:
        text: 셀 텍스트.

    Returns:
        토큰 수. 바이트 추정이면 UTF-8 바이트 수를 3으로 나눠 올림한 값.
    """
    enc = _encoding()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return -(-len(text.encode("utf-8")) // 3)
