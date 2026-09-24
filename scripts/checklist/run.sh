#!/usr/bin/env bash
# 한 동작 체크리스트. samples/의 세 프로젝트를 임시 폴더에 복사해 임시 앱 홈에
# 등록하고, madang serve와 실제 claude로 다섯 항목을 확인한 뒤 항목별
# PASS/FAIL과 근거, 호출당 입력 수치를 보고서(md)에 쓴다. 실제 ~/.madang과
# 사용자 폴더는 건드리지 않고 원격을 쓰지 않는다.
#
# 사용: bash scripts/checklist/run.sh
# 앱 홈 설정은 madang init이 만든 기본 config.yaml 그대로 쓴다(러너 인자·routes를
# 덧대지 않는다). 바꾸는 것은 라우팅 단계의 모델뿐이다.
#
# 환경: CHECKLIST_REPORT  보고서 경로 (기본: 작업 폴더/checklist.md)
#       CHECKLIST_WORK    작업 폴더 (기본: 새 임시 폴더)
#       CHECKLIST_MODEL   라우팅 단계마다 쓸 claude 모델 (기본: claude-sonnet-5)
#       MADANG_CORE_BIN   core 실행 파일. 주면 uv 대신 이것으로 madang을 돌린다
#                         (예: Madang.app/Contents/app/resources/madang-core/madang)
# 종료 코드: 모든 항목 PASS면 0, FAIL이 있으면 1, 중간에 멈추면 그 밖의 값.

set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
tmp="${TMPDIR:-/tmp}"
work="${CHECKLIST_WORK:-$(mktemp -d "${tmp%/}/madang-checklist.XXXXXX")}"
report="${CHECKLIST_REPORT:-$work/checklist.md}"

if [ ! -d "$here/node_modules" ]; then
  (cd "$here" && npm ci --no-audit --no-fund --silent)
fi

echo "work:   $work"
echo "report: $report"
echo "core:   ${MADANG_CORE_BIN:-uv run --project $repo/core madang}"
uv run --quiet --project "$repo/core" python "$here/checklist.py" \
  --repo "$repo" --work "$work" --report "$report" \
  --model "${CHECKLIST_MODEL:-claude-sonnet-5}"
