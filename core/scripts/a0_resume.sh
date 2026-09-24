#!/usr/bin/env bash
# Resume check: one page taken through three independent runs (design, write,
# review), each in a fresh claude session, in a temporary app home. Prints the
# input estimate and the reported usage of each run, then checks that there
# are three run records, three run commits after init, and that every input
# estimate stays within the budget.
#
# Usage: bash scripts/a0_resume.sh
# Env:   A0_HOME    app home to use (default: a new temporary folder)
#        A0_BUDGET  input estimate limit per run in tokens (default: 35000)

set -euo pipefail

core="$(cd "$(dirname "$0")/.." && pwd)"
tmp="${TMPDIR:-/tmp}"
home="${A0_HOME:-$(mktemp -d "${tmp%/}/madang-a0.XXXXXX")}"
budget="${A0_BUDGET:-35000}"

madang() {
  uv run --quiet --project "$core" madang "$@"
}

step() {
  local label="$1" model="$2" effort="$3" request="$4"
  echo "== $label: claude/$model/$effort"
  if ! madang run "$page" --home "$home" --tool claude --model "$model" \
      --effort "$effort" "$request"; then
    echo "   (run reported a problem; see runs/ in $home)"
  fi
}

echo "app home: $home"
madang init --home "$home"
page="$(madang page new --home "$home" --title "이력서" --slug resume \
  --kind design)"
echo "page: $page"

step design claude-opus-5-5 medium \
  "이력서 페이지를 설계한다. 대상은 5년 차 백엔드 개발자(가상의 인물)다. \
섹션 구성과 각 섹션의 데이터 구조(JSON 필드)를 설계 문서 하나로 blocks/에 \
남기고, state.md의 목표·결정 사항·다음 할 일을 작성 단계가 바로 시작할 수 \
있게 갱신한다."

step write claude-sonnet-5 medium \
  "state.md의 다음 할 일에 따라 설계 문서대로 이력서 데이터를 blocks/에 JSON \
파일로 작성하고 artifacts에 등록한다. 내용은 가상의 인물로 채운다. 끝나면 \
state.md를 검토 단계에 맞게 갱신한다."

step review claude-opus-5-5 low \
  "작성된 이력서 데이터를 설계 문서와 대조해 검토한다. 지적 사항을 검토 문서 \
하나로 blocks/에 남기고 artifacts에 등록한 뒤, state.md의 현재 상태와 다음 \
할 일을 갱신한다."

uv run --quiet --project "$core" python - "$home" "$page" "$budget" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

home, page, budget = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
page_dir = next(home.glob(f"spaces/*/pages/{page}"))
records = sorted(
    (json.loads(p.read_text()) for p in page_dir.glob("runs/*.json")),
    key=lambda r: r["n"],
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(home), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


rows = [
    ("run", "model/effort", "input_est", "usage.input", "cached", "output",
     "seconds", "status", "commit"),
]
for r in records:
    rel = (page_dir / f"runs/{r['n']}.json").relative_to(home)
    rows.append((
        str(r["n"]),
        f"{r['model']}/{r['effort']}",
        str(r["input"]["total_est"]),
        str(r["usage"]["input"]),
        str(r["usage"]["cached"]),
        str(r["usage"]["output"]),
        f"{r.get('duration') or 0:.1f}",
        str(r.get("result_status")),
        git("log", "-1", "--format=%h", "--", str(rel)),
    ))
print()
print("| " + " | ".join(rows[0]) + " |")
print("|" + "---|" * len(rows[0]))
for row in rows[1:]:
    print("| " + " | ".join(row) + " |")

subjects = git("log", "--format=%s").splitlines()
run_commits = [s for s in subjects if s.startswith(f"[{page}] run ")]
checks = {
    "3 run records": len(records) == 3,
    "3 run commits + init": len(run_commits) == 3
    and subjects[-1] == "[home] init"
    and len(subjects) == 4,
    f"every input_est <= {budget}": all(
        r["input"]["total_est"] <= budget for r in records
    ),
    "clean app home": git("status", "--porcelain") == "",
}
print()
for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
print()
print("\n".join(subjects))
sys.exit(0 if all(checks.values()) else 1)
PY
