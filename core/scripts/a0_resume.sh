#!/usr/bin/env bash
# Resume check: one page taken through three independent runs (design, write,
# review), each in a fresh claude session. The app home and the project folder
# are new temporary folders; the project is a git repository whose .madang/
# records stay out of git. Prints the input estimate and the reported usage of
# each run, then checks that there are three run records, that every input
# estimate stays within the budget, that the app home is not a git repository,
# and that the project repository has no new commits and no .madang/ changes.
#
# Usage: bash scripts/a0_resume.sh
# Env:   A0_HOME     app home to use (default: a new temporary folder)
#        A0_PROJECT  project folder to use (default: a new temporary folder)
#        A0_BUDGET   input estimate limit per run in tokens (default: 35000)

set -euo pipefail

core="$(cd "$(dirname "$0")/.." && pwd)"
tmp="${TMPDIR:-/tmp}"
home="${A0_HOME:-$(mktemp -d "${tmp%/}/madang-a0-home.XXXXXX")}"
project="${A0_PROJECT:-$(mktemp -d "${tmp%/}/madang-a0-project.XXXXXX")}"
budget="${A0_BUDGET:-35000}"

madang() {
  uv run --quiet --project "$core" madang "$@"
}

step() {
  local label="$1" model="$2" effort="$3" request="$4"
  echo "== $label: claude/$model/$effort"
  if ! madang run "$page" --home "$home" --tool claude --model "$model" \
      --effort "$effort" "$request"; then
    echo "   (run reported a problem; see .madang/pages/$page/runs/ in $project)"
  fi
}

echo "app home: $home"
echo "project:  $project"
madang init --home "$home"
if [ ! -d "$project/.git" ]; then
  git -C "$project" init -q -b main
  printf '# 이력서 작업\n' > "$project/README.md"
  git -C "$project" add README.md
  git -C "$project" -c user.name=a0 -c user.email=a0@localhost \
    -c commit.gpgsign=false commit -q -m "init"
fi
project_id="$(madang project add "$project" --id resume-work --home "$home")"
page="$(madang page new --home "$home" --project "$project_id" \
  --title "이력서" --slug resume --kind design)"
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

uv run --quiet --project "$core" python - "$home" "$project" "$page" \
  "$budget" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

home, project = Path(sys.argv[1]), Path(sys.argv[2])
page, budget = sys.argv[3], int(sys.argv[4])
page_dir = project / ".madang" / "pages" / page
records = sorted(
    (json.loads(p.read_text()) for p in page_dir.glob("runs/*.json")),
    key=lambda r: r["n"],
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


rows = [
    ("run", "model/effort", "input_est", "usage.input", "cached", "output",
     "seconds", "status", "unknown"),
]
for r in records:
    rows.append((
        str(r["n"]),
        f"{r['model']}/{r['effort']}",
        str(r["input"]["total_est"]),
        str(r["usage"]["input"]),
        str(r["usage"]["cached"]),
        str(r["usage"]["output"]),
        f"{r.get('duration') or 0:.1f}",
        str(r.get("result_status")),
        str(len(r.get("unknown_files") or [])),
    ))
print()
print("| " + " | ".join(rows[0]) + " |")
print("|" + "---|" * len(rows[0]))
for row in rows[1:]:
    print("| " + " | ".join(row) + " |")

checks = {
    "3 run records": len(records) == 3,
    f"every input_est <= {budget}": all(
        r["input"]["total_est"] <= budget for r in records
    ),
    "app home is not a git repository": not (home / ".git").exists(),
    "no new project commits": git("log", "--format=%s").splitlines()
    == ["init"],
    "records stay out of git": ".madang" not in git(
        "status", "--porcelain", "--untracked-files=all", "--ignored=no"
    ),
}
print()
for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
PY
