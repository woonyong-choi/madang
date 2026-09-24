#!/usr/bin/env bash
# 설치된 앱의 웹 엔진(KCEF) 번들을 확인한다. macOS용.
#
# 사용:
#   bash scripts/check-webengine.sh bundle [앱 경로]   앱을 띄우지 않고 번들만 검사한다.
#   bash scripts/check-webengine.sh probe [앱 경로]    앱 화면 없이 CEF를 띄워 로컬 html을 읽어 본다.
#   bash scripts/check-webengine.sh run [앱 경로]      앱을 터미널에서 띄우고 로그를 남긴다.
#
# 앱 경로를 주지 않으면 /Applications/Madang.app을 쓴다.
# 번들 폴더는 앱 설정 폴더(MADANG_APP_CONFIG_DIR, 없으면 ~/Library/Application Support/Madang)의
# kcef-bundle/이다.
#
# bundle: 파일만 본다. 설치 표식(install.lock), 받은 릴리스 표식, jcef 네이티브 라이브러리,
#   CEF 프레임워크와 jcef 헬퍼, 네이티브 라이브러리가 찾는 org/cef 클래스가 앱의 jcef jar에 있는지.
#   앱에 번들 검사 기능이 있으면 그 결과(창 없이 도는 --check-webengine)도 함께 보인다.
# probe: 앱의 --probe-webengine으로 문서 탭과 같은 길로 CEF를 띄우고 브라우저 하나로 문서 탭 호스트
#   (로컬 html)를 읽는다. 번들이 없으면 먼저 받는다. 작은 창이 잠깐 떴다 닫힌다. 로그를
#   ~/madang-webengine-probe.log에 남기고 앱의 종료 코드로 끝난다(0 읽기 완료, 1 실패, 2 재시작 필요).
#   화면이 있는 터미널에서 돌리거나, 원격 셸이면 `launchctl asuser $(id -u)`로 사용자 세션에서 돌린다.
# run: 앱을 이 터미널에서 띄운다. 표준 출력·오류를 ~/madang-webengine.log에 남기고, JVM이
#   죽으면 오류 파일을 ~/madang-hs_err_<pid>.log에 남긴다. 페이지를 눌러 문서 탭을 연 뒤 앱을 닫는다.
#   화면이 있는 터미널에서 돌려야 한다.

set -euo pipefail

mode="${1:-}"
app="${2:-/Applications/Madang.app}"
config_dir="${MADANG_APP_CONFIG_DIR:-$HOME/Library/Application Support/Madang}"
bundle="$config_dir/kcef-bundle"
log="$HOME/madang-webengine.log"

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

# 앱 번들 안 jar 폴더.
app_jars() {
  echo "$app/Contents/app"
}

# 앱 번들 안에서 이름이 맞는 첫 jar. 없으면 빈 문자열.
app_jar() {
  # 패턴을 펼치려고 $1에 따옴표를 두지 않는다.
  # shellcheck disable=SC2206
  local found=("$(app_jars)"/$1)
  [[ -f "${found[0]}" ]] && echo "${found[0]}" || true
}

check_bundle() {
  local problems=0
  echo "app: $app"
  echo "bundle: $bundle"
  if [[ ! -d "$bundle" ]]; then
    echo "  - 번들 폴더가 없다(아직 받지 않았다). 앱에서 문서 탭을 열면 받는다."
    return 1
  fi
  if [[ -f "$bundle/install.lock" ]]; then
    echo "  ok install.lock"
  else
    echo "  !! install.lock 없음(설치를 마치지 않았다)"
    problems=1
  fi
  if [[ -f "$bundle/madang-webengine-release" ]]; then
    echo "  ok 받은 릴리스: $(cat "$bundle/madang-webengine-release")"
  else
    echo "  !! 받은 릴리스 표식 없음(고정 전 번들이다. 새 앱이 지우고 다시 받는다)"
    problems=1
  fi
  for path in "libjcef.dylib" \
    "Frameworks/Chromium Embedded Framework.framework" \
    "Frameworks/jcef Helper.app"; do
    if [[ -e "$bundle/$path" ]]; then
      echo "  ok $path"
    else
      echo "  !! 없음: $path"
      problems=1
    fi
  done
  echo "  Frameworks/:"
  ls -1 "$bundle/Frameworks" 2>/dev/null | sed 's/^/    /' || echo "    (없음)"

  local jar
  jar="$(app_jar 'jcef-*.jar')"
  if [[ -f "$bundle/libjcef.dylib" && -n "$jar" ]]; then
    local missing
    missing="$(comm -13 \
      <(unzip -Z1 "$jar" | grep '\.class$' | sed 's/\.class$//' | sort -u) \
      <(strings -a "$bundle/libjcef.dylib" | grep -E '^org/cef/[A-Za-z0-9_/$]+$' | sort -u))"
    if [[ -z "$missing" ]]; then
      echo "  ok libjcef.dylib가 찾는 클래스가 모두 $(basename "$jar")에 있다"
    else
      echo "  !! libjcef.dylib가 찾는 클래스가 $(basename "$jar")에 없다(CEF를 띄우면 죽는다):"
      echo "$missing" | sed 's/^/    /'
      problems=1
    fi
  elif [[ -z "$jar" ]]; then
    echo "  -- 앱에서 jcef jar를 찾지 못해 클래스 대조는 건너뛴다: $(app_jars)"
  fi

  # 앱에 번들 검사 기능이 있을 때만 부른다. 없는 앱에 인자를 주면 창이 뜨기 때문이다.
  local desktop_jar
  desktop_jar="$(app_jar 'desktop-[0-9a-f]*.jar')"
  if [[ -n "$desktop_jar" ]] &&
    unzip -l "$desktop_jar" 'madang/desktop/WebEngineBundle.class' >/dev/null 2>&1; then
    echo "앱의 번들 검사:"
    if ! "$app/Contents/MacOS/Madang" --check-webengine | sed 's/^/  /'; then
      problems=1
    fi
  else
    echo "-- 이 앱에는 번들 검사 기능이 없다(고치기 전 빌드)."
  fi
  return "$problems"
}

probe_app() {
  local launcher="$app/Contents/MacOS/Madang"
  local probe_log="$HOME/madang-webengine-probe.log"
  [[ -x "$launcher" ]] || { echo "앱 실행 파일이 없다: $launcher" >&2; exit 1; }
  local desktop_jar
  desktop_jar="$(app_jar 'desktop-[0-9a-f]*.jar')"
  # 진단 기능이 없는 앱에 인자를 주면 창이 뜨므로 먼저 확인한다.
  if [[ -z "$desktop_jar" ]] ||
    ! unzip -l "$desktop_jar" 'madang/desktop/WebEngineProbe.class' >/dev/null 2>&1; then
    echo "이 앱에는 엔진 진단 기능이 없다(고치기 전 빌드)." >&2
    exit 1
  fi
  cd "$HOME"
  set +e
  JAVA_TOOL_OPTIONS="-XX:ErrorFile=$HOME/madang-hs_err_%p.log" "$launcher" --probe-webengine 2>&1 |
    tee "$probe_log"
  local code="${PIPESTATUS[0]}"
  set -e
  echo "== 종료 코드 $code (로그: $probe_log)"
  return "$code"
}

run_app() {
  local launcher="$app/Contents/MacOS/Madang"
  [[ -x "$launcher" ]] || { echo "앱 실행 파일이 없다: $launcher" >&2; exit 1; }
  {
    echo "== $(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "== macOS $(sw_vers -productVersion) $(uname -m)"
    check_bundle || true
    echo "== 앱 실행: $launcher"
  } 2>&1 | tee "$log"
  echo "페이지를 눌러 문서 탭을 연 뒤 앱을 닫는다. 로그: $log"
  cd "$HOME"
  set +e
  JAVA_TOOL_OPTIONS="-XX:ErrorFile=$HOME/madang-hs_err_%p.log" "$launcher" 2>&1 | tee -a "$log"
  local code="${PIPESTATUS[0]}"
  set -e
  echo "== 종료 코드 $code" | tee -a "$log"
  ls -1t "$HOME"/madang-hs_err_*.log 2>/dev/null | head -1 | sed 's/^/== JVM 오류 파일: /' |
    tee -a "$log" || true
}

case "$mode" in
  bundle) check_bundle ;;
  probe) probe_app ;;
  run) run_app ;;
  *) usage ;;
esac
