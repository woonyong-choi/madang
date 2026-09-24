#!/usr/bin/env bash
# core를 Python 없이 도는 PyInstaller onedir 번들로 만든다.
#
# 결과: core/dist/madang-core/ (실행 파일 madang + _internal/)
# 앱 패키징(app에서 ./gradlew :desktop:packageDmg)이 이 폴더를 앱 리소스에 싣는다.
#
# - tiktoken 인코딩(cl100k_base)을 core/build/tiktoken에 미리 받아 번들에 넣는다.
#   이미 받아 두었으면 네트워크를 쓰지 않는다.
# - PyInstaller는 core 프로젝트 환경에 이번 실행만 얹는다(전역 설치 없음).
#
# 사용: bash scripts/build-core.sh

set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
core="$repo/core"
dist="$core/dist"
export TIKTOKEN_CACHE_DIR="$core/build/tiktoken"

mkdir -p "$TIKTOKEN_CACHE_DIR"
echo "tiktoken: $TIKTOKEN_CACHE_DIR"
uv run --quiet --project "$core" python -c \
  'import tiktoken; tiktoken.get_encoding("cl100k_base")'

uv run --quiet --project "$core" --with "pyinstaller>=6.10" \
  pyinstaller --noconfirm --clean --log-level WARN \
  --distpath "$dist" --workpath "$core/build/pyinstaller" \
  "$core/packaging/madang.spec"

# 번들이 Python 없이 뜨는지 확인한다.
"$dist/madang-core/madang" --help >/dev/null
echo "core: $dist/madang-core ($(du -sh "$dist/madang-core" | cut -f1))"
