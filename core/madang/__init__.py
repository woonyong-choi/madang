"""Madang 코어 패키지."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("madang")
except PackageNotFoundError:  # 설치 없이 소스 트리에서 실행하는 경우
    __version__ = "0.0.0"
