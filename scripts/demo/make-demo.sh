#!/usr/bin/env bash
# 데모 세 프로젝트(wiki, resume, code)를 만든다. 프로젝트마다 요청 대기
# 페이지와 실행 완료 페이지가 하나씩 생기고, 앱에서 "프로젝트 추가"만 하면
# 두 페이지가 보인다. 실행 완료 페이지는 임시 앱 홈과 저장소 core로 실제
# 에이전트 요청을 한 번씩 보내 만든다(기본 라우팅 표 그대로).
#
# 사용: bash scripts/demo/make-demo.sh
# 대상 폴더가 이미 있으면 지우지 않고 <대상>.bak-<시각>으로 옮긴 뒤 새로 만든다.
# 사용자 ~/.madang과 앱 설정은 건드리지 않는다.
#
# 환경: MADANG_DEMO_DIR   만들 폴더 (기본: ~/workspace/OSS/madang-demo)
#       MADANG_DEMO_WORK  임시 앱 홈과 core 로그를 둘 폴더 (기본: 새 임시 폴더)
# 종료 코드: 새 앱 홈에서 프로젝트마다 페이지 두 개가 보이면 0.

set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
tmp="${TMPDIR:-/tmp}"
dest="${MADANG_DEMO_DIR:-$HOME/workspace/OSS/madang-demo}"
work="${MADANG_DEMO_WORK:-$(mktemp -d "${tmp%/}/madang-demo.XXXXXX")}"

if [ -e "$dest" ]; then
  backup="$dest.bak-$(date +%Y%m%d-%H%M%S)"
  mv "$dest" "$backup"
  echo "moved:  $dest -> $backup"
fi

echo "dest:   $dest"
echo "work:   $work (앱 홈과 core 로그)"
uv run --quiet --project "$repo/core" python "$here/make_demo.py" \
  --repo "$repo" --dest "$dest" --work "$work"
