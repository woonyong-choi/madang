# madang-app

Madang 데스크톱 앱. Kotlin Multiplatform + Compose Multiplatform.

지금 타깃은 desktop(JVM: macOS, Windows)이다. Android·iOS는 이후에 추가한다.

## 설치 (macOS)

1. `Madang-1.0.0.dmg`를 열고 `Madang.app`을 원하는 폴더로 끌어 놓는다. Python은 필요 없다(core가 앱에 들어 있다).
2. 서명하지 않은 앱이라 처음 한 번은 Finder에서 앱을 Control-클릭 → "열기"를 누른다(막히면 시스템 설정 → 개인정보 보호 및 보안 → "그래도 열기", 또는 `xattr -dr com.apple.quarantine <경로>/Madang.app`).
3. 첫 화면의 온보딩에서 앱 홈 초기화 → 첫 프로젝트 폴더 고르기 → claude 로그인 확인 순서로 진행한다(로그인은 터미널에서 `claude`로 직접 한다).

## 요구 사항

- JDK 21
- Gradle은 설치하지 않아도 된다. 저장소의 wrapper(`./gradlew`)를 쓴다.

## 모듈

```
app/
├ shared/    공용 코드 (commonMain): core 연결, 이벤트 스트림, ViewModel, 화면
└ desktop/   JVM 데스크톱 진입점: 창, core 프로세스 기동, 앱 설정 파일, 가짜 core
```

- `CoreClient`: core 연결 하나. 생성된 API 클라이언트(`madang.api.client`)가 HTTP 클라이언트를
  함께 쓴다. `core.api(::PagesApi)`처럼 필요한 클라이언트를 얻는다.
- `CoreLocator`: 설정의 core 주소 → `<앱 홈>/core.port` → `http://127.0.0.1:7470` 순서로
  `/health`를 확인하고, 없으면 core를 띄운 뒤 응답할 때까지 기다린다.
- `EventStream`: `WS /events`를 `Flow`로 바꾼다. 끊기면 다시 붙고, 붙을 때마다 전체 재조회 신호
  (`Resync`)를 보낸다.
- 화면: 시작 → (전역 설정이 없으면) 온보딩 → 메인 ↔ 설정. 화면마다 ViewModel + `StateFlow`.
- 메인 화면은 3열이다: 프로젝트·태그 트리 / 페이지 카드 목록 / 가운데 열(탭 작업 공간). 창이 좁으면
  (목록 또는 프로젝트) + 본문 2열, 더 좁으면 한 열만 보인다.

## 프로젝트와 온보딩

- 프로젝트는 core에 등록한 로컬 폴더(보통 git 저장소)다. 페이지 기록은 그 폴더의 `.madang/`에
  있고, 전역 설정과 profile.md는 앱 홈(`~/.madang`)에 있다. 둘 다 core가 쓴다.
- 왼쪽 열의 프로젝트 줄은 제목(기본은 폴더 이름)을 보이고, 마우스를 올리면 폴더 경로가 뜬다.
- "+ 프로젝트"는 운영체제의 폴더 선택 대화상자를 열고, 고른 폴더를 `POST /projects`로 등록한다.
  core가 그 폴더에 `.madang/`을 만든다.
- 프로젝트 오른쪽 클릭의 "등록 해제"는 `DELETE /projects/{p}`다. 폴더와 기록은 그대로 남는다.
- 첫 실행(`GET /home`의 `initialized`가 거짓): 전역 설정 초기화(`POST /home`, 경로는 core가 알려 준
  앱 홈) → 첫 프로젝트 폴더 고르기(`POST /projects`) → 도구 확인 순서다.
- 도구 확인: Finder로 연 앱은 셸 PATH를 받지 않는다. 그래서 사용자의 로그인 셸
  (`$SHELL -lc 'command -v claude'`, codex도)이 찾은 절대 경로를 보여 주고 전역 config.yaml의
  `runners.claude.bin`·`runners.codex.bin`에 저장한다(`GET /config`로 원문을 받아 그 값만 고친 뒤
  `PUT /config`, 주석은 그대로). 못 찾으면 실행 파일 경로를 직접 넣고, 앱은 그 파일이 실행
  파일인지만 확인해 저장한다. 흔한 설치 위치를 뒤지는 추측은 하지 않는다.
- claude 로그인 확인은 저장한 경로로 `<경로> auth status`를 실행해 출력의 로그인 여부와 방식만
  본다. 로그인은 터미널에서 직접 하고, 로그인하지 않았어도 시작할 수 있다.

## 메인 화면 조작

| 키·동작 | 결과 |
|---|---|
| 위·아래 | 프로젝트 열: 프로젝트·태그 고르기. 목록 열: 페이지 고르고 열기 |
| 오른쪽 · Enter | 다음 열로(프로젝트 열에서 오른쪽은 접힌 프로젝트를 먼저 펼친다) |
| 왼쪽 · Backspace | 이전 열로(프로젝트 열에서 왼쪽은 펼친 프로젝트를 접거나 상위로) |
| Cmd/Ctrl+0 | 프로젝트 열 포커스 |
| Cmd/Ctrl+1 | 페이지 탭으로(가운데 열 포커스) |
| Cmd/Ctrl+2/3 | 목록 / 가운데 열 포커스 |
| Cmd/Ctrl+W | 활성 탭 닫기(페이지 탭은 닫지 않는다) |
| Cmd/Ctrl+Shift+] · [ | 다음 / 이전 탭 |
| Cmd/Ctrl+N | 고른 프로젝트에 새 페이지 |
| Cmd/Ctrl+K | 페이지 검색(제목·마지막 메시지·#태그) |
| M | 오른쪽 사이드바의 메모리 탭 열기·닫기 |
| Esc | 사이드바 닫기, 입력창에서 나오기, 페이지 탭으로 |
| 카드에 마우스 | 고정·태그·이동·삭제 빠른 동작 |
| 카드를 프로젝트·태그로 끌기 | 그 프로젝트로 이동, 그 태그 추가 |
| 오른쪽 클릭 | 프로젝트: 포커스·이름 변경·최근 삭제·등록 해제. 카드: 고정·태그·이동·삭제 |

목록은 고정된 페이지가 먼저이고, 프로젝트별 정렬(갱신·생성·제목)을 따른다. 날짜순이면 오늘·어제·지난
7일·지난 30일·월별로 묶는다. 필터는 상태와 태그로 건다.

## 문서 탭 = 렌더러

- 문서 탭(페이지 흐름, `.md` 파일, doc 블록, run 탭 본문)은 게시와 같은 렌더러 `templates/_runtime`을
  KCEF WebView에서 그대로 쓴다. 앱에 따로 마크다운 렌더러는 없다. 빌드가 렌더러 파일을 jar의
  `madang-runtime/`에 싣고, 앱은 앱 설정 폴더의 `document-runtime/`에 풀어 `app.html`을 연다
  (`DocumentRuntime`). 엔진이 준비 중이면 브라우저 탭처럼 진행을, 엔진이 없는 플랫폼이면 원문을 보인다.
- 페이지 흐름은 디스크의 page.md(`<프로젝트>/.madang/pages/<id>/page.md`) 원문이다. 블록 머리 주석
  (`<!-- bNN | 시각 | 역할 | … -->`)을 렌더러가 요청·라우팅·결과·묻는 블록·답 컴포넌트로 그리고, 라우팅과
  실행 기록은 접어 둔다. page.md를 읽지 못하면 core가 준 머리부로 같은 모양을 만든다. doc·data 같은 파일
  블록은 흐름 순서 자리에 끼우고, 보내는 중인 메시지는 끝에 흐리게 붙는다(`main/PageDocument.kt`).
- view 펜스(```` ```view 이름 data=./a.json ````)는 core 등록부(`GET /viewers`)가 선언한 뷰어 폴더
  (pinned면 앱 홈 `cache/<해시>/<이름>/`)와 문서 폴더 기준 데이터 파일로 풀어(`main/DocumentViews.kt`)
  렌더러의 sandbox iframe에 넣는다. 앱 테마의 토큰 다섯 개(`--app-bg`·`--app-text`·`--app-accent`·
  `--app-font`·`--app-radius`)를 iframe과 문서 바탕에 준다. 데이터 스키마 검사는 core의 일이다.
- 링크는 렌더러 호스트가 `madang-app://…`로 알리고 앱이 그 탐색을 막아 탭을 연다(`DocumentBridge`).
  view 펜스 옆 "데이터"는 그 데이터 파일을 데이터 탭으로, 블록·실행의 "열기"는 그 탭으로, 상대 링크는
  확장자 규칙대로, `http(s)`는 브라우저 탭으로 연다. 호스트 CSP는 뷰어 스크립트가 돌도록 `script-src`에
  `'unsafe-inline'`을 둔다.

## 가운데 열 탭

- 탭 종류는 여섯 가지로 고정이다: 문서 · 터미널 · 채팅 · 브라우저 · 디프 · 데이터. 터미널과 채팅은
  아직 자리만 있다. 종류는 열기 요청과 파일 확장자로만 정하고 내용을 보고 짐작하지 않는다
  (`main/TabKinds.kt`의 표 하나):

  | 연 것 | 탭 |
  |---|---|
  | `.md` 파일 | 문서 |
  | `.json` · `.yaml` · `.yml` · `.csv` 파일 | 데이터 |
  | `.html` 파일, URL | 브라우저(파일은 `file://`) |
  | git diff | 디프 |
  | PTY / kind=chat 페이지 | 터미널 / 채팅(아직 열리지 않음) |
  | 그 밖의 파일 | 문서 탭의 코드 보기(편집 없음, "외부 편집기로 열기") |

- 더블클릭 = 열기, 항상. 첫 탭 "페이지"는 블록 흐름이며 닫을 수 없다. 흐름에서 블록이나 실행을
  더블클릭하거나 "열기"를 누르면 그 종류의 탭이 열리고, 이미 열려 있으면 그 탭으로 간다. doc·data·view 블록은 블록 파일의
  확장자, site 블록은 `url`, code 블록은 `path`(core가 알려 준 작업 폴더 기준, `GET /projects/{p}/git/status`의
  `folder`)를 연다. term 블록은 터미널 탭이 생길 때까지 열리지 않는다. run 탭과 페이지 탭은 문서 탭이다.
- 탭 안 오른쪽 서랍(접을 수 있음): 문서는 미리보기/원본, 데이터는 표/트리/원문, run은 입력 구성·사용량·바뀐
  파일·이벤트 로그(`GET /pages/{p}/runs/{n}/events`). run 탭 본문에는 그 run을 일으킨 요청과 run이
  남긴 블록을 렌더러로 보인다.
- 데이터 탭: JSON·YAML·CSV를 표(최상위 목록·매핑)와 트리로 본다. 블록 파일은 "원문"에서 줄 번호
  편집기로 고쳐 저장한다(`PUT /pages/{p}/blocks/{b}`). core가 거부하면 이유를 그 줄 옆에 보인다. 작업
  폴더 파일은 읽기만 한다.
- 디프 탭: 페이지 제목 옆 "디프"로 연다. `GET /projects/{p}/git/diff?page=`의 통합 diff를 파일별로
  접고 펼친다. `git.changed` 이벤트가 오면 다시 받는다. git 저장소가 아니면(409 `no_repo`) 그렇다고만
  보인다. 줄 댓글은 아직 없다.
- 브라우저 탭: KCEF(Chromium) 웹 화면. 로컬 파일과 localhost URL을 연다. core가 `runs.opened`를 보내면
  열린 페이지가 그 프로젝트일 때 그 URL을 브라우저 탭으로 연다. 엔진 번들은 브라우저 탭을 처음 열 때
  앱 설정 폴더의 `kcef-bundle/`에 내려받고(진행률 표시), 캐시는 `kcef-cache/`에 둔다. 다시 시작하라고 하면
  앱을 다시 띄운다.
- 탭 세트는 페이지마다 앱 설정(`pageTabs`)에 저장되어 재시작 뒤에도 되살아난다. 페이지를 바꾸면 탭
  세트가 통째로 바뀐다. 탭을 닫아도 블록·파일은 남는다.

## 가운데 열 아래 입력창과 페이지 도구

- 입력창: 대상은 활성 탭이다. 페이지 탭과 run 탭에서는 "페이지에게", doc·data 탭에서는
  "[블록 이름]에게"(`target.block`)로 보낸다. Enter와 Cmd/Ctrl+Enter는 보내기, Shift+Enter는 줄바꿈.
  한글처럼 입력기가 글자를 조합하는 중의 Enter는 조합 확정이라 보내지 않는다. 누르는 버튼은 보내기 하나이고
  종류·모델·머지·게시는 core 정책이 정한다. 입력을 멈추고 300ms 뒤 `GET /pages/{p}/preview-input`으로 다음
  호출의 입력 토큰과 도구/모델을 받아 오른쪽에 보인다(보이기만 한다).
- 보낸 메시지는 core 응답 전에 본문 끝에 흐리게 붙고, core 페이지에 같은 메시지 블록이 생기면
  그 블록으로 바뀐다. 보내기에 실패하면 빠지고 입력창에 문장이 되돌아온다.
- 오른쪽 사이드바(페이지 제목 옆 "메모리" 또는 M): 지금 · 파일 · 메모리 · git · 포트 · 기록 탭. 보이는 탭
  하나만 core에서 내용을 받는다. 지금 탭 밖의 탭은 열린 페이지(없으면 고른 프로젝트)를 따른다.
- 상태 글리프 하나를 카드·run 카드·지금 탭이 함께 쓴다: 스피너 실행 중, 호박색 물음표 사람 필요(`flow.waiting`·
  `ask.created`), 초록 체크 완료, 빨간 점 실패(`error`·`cancelled`·`blocked`), 회색 점 유휴(run 없음). 열려 있지
  않은 페이지에서 run이 끝나면 그 카드 제목이 굵어지고, 페이지를 열면 풀린다.
- 지금 탭: 위에 구독 사용량(`GET /usage`, 도구별 5시간·7일 창). core가 한도 비율을 주면 막대와 비율을, 주지
  않으면 쓴 토큰만 보인다. 경고는 core의 `warn`만 쓴다. 아래에 모든 프로젝트의 진행 중 run(최근에 시작한 것부터),
  사람을 기다리는 페이지, 30분 안에 끝난 run(최근 것부터)이다. 앱이 켜진 뒤 끝난 run은 이벤트의 끝난 시각, 그 전
  것은 카드의 마지막 run과 갱신 시각으로 판단한다. 줄을 누르면 마지막 호출의 입력 구성(진행 중이면
  `run.assembled`, 아니면 `GET /pages/{p}/runs/{n}`), "로그"를 누르면 이벤트 로그의 마지막 30줄(진행 중이면
  `run.progress`가 이어 붙는다)을 펼친다. 두 번 누르면 그 페이지를 연다.
- 파일 탭: `GET /projects/{p}/files`의 트리(페이지가 열려 있으면 그 워크트리). `.madang/`은 맨 위에 접힌 채로
  있고 다른 폴더는 펼쳐 있다. 렌즈는 전체 / 이 페이지(페이지가 열려 있을 때) / 변경됨(git 저장소가 아니면 그렇다고만
  보인다). "실행" 배지는 core가 `runs:` 선언에서 붙인 폴더에만 있고, 누르거나 그 폴더를 두 번 누르면 core가 실행
  대상을 띄운다(`POST /projects/{p}/runs/{name}/start`, 준비되면 `runs.opened`로 브라우저 탭). 파일을 두 번
  누르면 가운데 열 탭 규칙대로 연다.
- git 탭: `GET /projects/{p}/git/status`가 저장소가 아니라고 하면 "git 시작"(`POST .../git/init`) 하나만
  보인다. 저장소면 브랜치와 풀·푸시, 변경(파일별 스테이지·모두 스테이지)과 스테이지된 파일, 커밋 메시지와 커밋,
  브랜치 목록, 워크트리와 그 워크트리를 쓰는 페이지, 최근 커밋 20개다. 조작은 모두 core git API이고 core가 거부하면
  이유를 위에 보인다. `git.changed`가 오면 다시 받는다.
- 포트 탭: core가 관찰한 열린 포트(`GET /projects/{p}/ports`, `ports.changed`로 갱신). 선언된 실행 대상이 연
  포트는 그 이름을, 아니면 "선언으로 저장"을 보인다. 이름을 적어 저장하면 `POST .../ports/{port}/declare`로
  `runs:`에 선언된다. 두 번 누르면 `http://localhost:<포트>`를 브라우저 탭으로 연다.
- 기록 탭: 열린 페이지의 run, 최근 것부터. 모델, 고른 이유(같은 run의 router 메시지), 입력·출력 토큰, 결과를
  보이고 누르면 그 run 탭을 연다.
- 시스템 알림: run 완료·실패와 묻는 블록(`ask.created`, 사람 결정 `flow.waiting`)을 운영체제 알림으로 알린다.
  같은 질문은 한 번만 알린다. 알림을 누르면(플랫폼이 알려 줄 때) 그 페이지를 연다. 설정 화면 "알림"에서
  끈다(앱 설정 `notifications`). 지금 탭에서 물음표(사람 필요) 줄은 한 번만 눌러도 그 페이지를 연다.
- 읽지 않음은 앱 설정(`unread`)에 저장되어 재시작 뒤에도 카드가 굵게 남는다.
- 메모리 탭은 Profile / Brief / Ledger를 언제나 이 순서로 위에서 아래로
  보인다. 층마다 머리부는 최상위 키별 입력칸(값은 `키:` 뒤의 원문, 고친 키의 줄만 바뀐다), 본문은 원문 그대로
  보인다(문서 렌더러가 붙기 전까지). "원문"을 켜면 파일 전체를 줄 번호 편집기로 고친다. 저장은 층마다 하고,
  core 검사기가 거부하면 문제를 그 키 입력칸 아래·본문 아래·원문 편집기의 줄 옆에 붙인다.
- 미등록 파일: `page.unknown_files` 이벤트가 오면 제목 아래 노란 띠가 뜬다. 띠를 누르면 목록이
  열리고 파일마다 산출물로 / 유지 / 삭제를 고른다.
- 사람 결정: `flow.waiting` 이벤트가 오면 페이지 위에 질문과 선택지 카드가 뜬다. 고르면 답을 보내고
  flow가 다시 돌면(`run.started`) 사라진다. 정책이 머지·게시를 멈춘 묻는 블록(결정에 `ask`가 있음)이면
  카드 제목이 "묻는 블록"이 되고 거부 이유를 함께 보이며, 답은 `POST /pages/{p}/asks/{id}/answer`로 간다.
- 결과 블록: run이 없을 때 문서 아래에 마지막으로 끝난 run의 자동 머지·게시 상태를 보인다. 완료(머지 해시·게시
  번호)는 core recorder의 되돌리기 기록(`runs/<n>.undo.json`)과 `publish.done`, 거부는 `ask.created` 이벤트와
  기다리는 결정의 `ask`, 대기는 그 run이 마지막이고 페이지가 `busy`인 동안이다.
  "되돌리기"는 `POST /pages/{p}/runs/{n}/undo`(core가 기록대로 게시·머지·페이지 파일을 되감는다. 거부하면 이유를
  상태 줄에), "다시 실행"은 그 run을 일으킨 요청을 같은 대상에게 다시 보낸다(보내기와 같은 길).
- 최근 삭제: 프로젝트 오른쪽 클릭 메뉴에서 연다. 등록한 모든 프로젝트의 `.madang/trash/`에 옮겨 둔
  페이지·블록을 최신순으로 보고 복구한다.
- 시작 화면에서 core에 연결하지 못하면 그 자리에서 core 주소를 고쳐 다시 연결할 수 있다.

앱은 앱 홈과 프로젝트의 `.madang/` 파일을 쓰지 않는다. 읽는 것은 `core.port`, 열린 페이지의 page.md와 마지막
run의 되돌리기 기록뿐이다. 작업 폴더 파일은 파일 탭(코드 보기·데이터)에서 읽기만 한다. 앱이 쓰는 파일은 앱 설정 `settings.json`과 브라우저 엔진 번들·캐시다(macOS `~/Library/Application Support/Madang`, Windows `%APPDATA%\Madang`,
그 밖 `~/.config/madang`, `MADANG_APP_CONFIG_DIR`로 변경).

## 명령

모든 명령은 `app/`에서 실행한다. Windows에서는 `gradlew.bat`을 쓴다.

```sh
./gradlew :shared:test          # 공용 모듈 테스트
./gradlew :desktop:test         # 데스크톱 모듈 테스트
./gradlew :desktop:run          # 앱 실행
./gradlew :desktop:compileKotlin
./gradlew ktlintCheck           # 코드 스타일 검사
./gradlew ktlintFormat          # 코드 스타일 자동 수정
```

코드 스타일은 Android Kotlin 스타일 가이드(ktlint `android_studio`)를 따른다. 규칙은 `.editorconfig`에 있다.

자동 확인용 실행: `MADANG_SMOKE=1`이면 첫 화면을 그린 뒤 3초 후 스스로 종료한다(exit 0).

```sh
MADANG_SMOKE=1 ./gradlew :desktop:run
```

떠 있는 실제 core로 한 동작(보내기 → 결과 블록의 게시 상태 → 되돌리기)을 화면 없이 확인하려면
`RealCoreOneActionTest`를 쓴다. `MADANG_REAL_CORE_URL`이 없으면 아무것도 하지 않는다. 에이전트 호출이 한 번
들기 때문에 임시 앱 홈과 `policy.auto_publish`·`publish:`가 있는 임시 프로젝트로 돌린다.

```sh
MADANG_REAL_CORE_URL=http://127.0.0.1:7470 MADANG_REAL_PROJECT=<프로젝트 id> \
  MADANG_REAL_PAGE=<페이지 id> MADANG_REAL_REQUEST="<요청>" MADANG_REAL_LOG=<기록 파일> \
  ./gradlew :desktop:test --tests 'madang.desktop.RealCoreOneActionTest'
```

## core 연결

`./gradlew :desktop:run`은 떠 있는 core가 없으면 `uv run --project ../core madang serve`로
core를 띄운다. 설정 화면의 "core 실행 파일"을 지정하면 `<파일> serve`를 쓴다. 패키지된 앱은
리소스 폴더의 동봉 core(`madang-core/madang`, PyInstaller onedir)를 띄운다. 어느 경우든 로그인
셸의 PATH(`$SHELL -lc`)를 core 환경으로 넘겨, 에이전트가 부르는 `madang`과 도구를 찾게 한다.
로그인 셸에서 PATH를 얻지 못하면 앱의 PATH를 그대로 물려준다. 실패하면 시작 화면에 원인과
"다시 시도"가 보인다.

core 없이 화면을 개발하려면 가짜 core를 쓴다. `../core/openapi.yaml`의 응답 예시로 답하고,
연결되면 계약의 이벤트 예시를 차례로 보낸다. 앱 설정 파일은 쓰지 않는다.

```sh
MADANG_FAKE_CORE=1 ./gradlew :desktop:run                      # 전역 설정 없음 → 온보딩
MADANG_FAKE_CORE=1 MADANG_FAKE_HOME=1 ./gradlew :desktop:run   # 메인 화면부터
```

페이지가 있는 화면을 보려면 픽스처를 쓴다. `desktop/src/test/resources/fixture-home/`의
프로젝트·페이지·블록 파일로 답하고, 고정·이동·삭제 같은 요청은 메모리에만 반영하며 이벤트를 보낸다.

```sh
MADANG_FAKE_CORE=1 MADANG_FAKE_FIXTURE=src/test/resources/fixture-home ./gradlew :desktop:run
```

픽스처는 메시지를 받으면 run 하나를 흉내 낸다. `run.*` 이벤트를 차례로 보내고, 끝나면
router·agent 메시지와 run 기록을 붙이고 미등록 파일(`blocks/scratch-<n>.txt`) 하나를 남긴다.
끝나면 정책 단계로 게시했다고 알린다(`publish.done`). 문장에 "결정"이 들어 있으면 도중에 `flow.waiting`으로
선택지를 묻고, 답하면 마저 끝낸다. 문장에 "정책"이 들어 있으면 정책이 게시를 멈추고 묻는 블록
(`ask.created`, merge·retry·stop)을 남긴다. merge면 게시하고, retry면 다시 돌고, stop이면 멈춘다. 되돌리기는
그 run의 게시를 되감고 두 번째부터는 409다. 메모리
저장은 ledger.md의 머리부 필수 키·status 값·필수 절·토큰 상한을 검사한다. 지운 페이지는 최근
삭제에서 되살릴 수 있다.

`./gradlew :desktop:test`는 이 픽스처로 메인 화면을 화면 밖에서 그려
`desktop/build/screenshots/`에 `wide.png`(3열), `narrow.png`(2열), `page.png`(1열)를 남긴다.
메시지를 보내 run 카드가 붙는 과정(`message-running.png`, `message-done.png`)과 사람 결정 카드·메모리
검사 오류(`decision-memory.png`), 메모리 탭의 세 층과 머리부 폼 검사 오류(`memory-tab.png`), 데이터 탭의 표
(`tabs-data.png`), 디프 탭(`tabs-diff.png`), 엔진을 처음 내려받는 브라우저 탭(`tabs-browser.png`), 사이드바의
지금 탭(`side-now.png`), 파일 탭(`side-files.png`), git 탭(`side-git.png`), 포트 탭(`side-ports.png`)도 남긴다.
픽스처의 `git/<프로젝트 id>.diff`가 그 프로젝트의 작업 트리 diff이고, 그 파일이 없는 프로젝트는 git 저장소가
아니다. `git/<프로젝트 id>.json`은 브랜치·워크트리·로그, `files/<프로젝트 id>.json`은 파일 트리(전체 렌즈와
페이지별 이 페이지 렌즈), `ports.json`은 프로젝트별 관찰 포트, `usage.json`은 사용량이다. 스테이지·커밋·git 시작·
포트 선언은 메모리에만 반영하고 `git.changed`·`ports.changed`를 낸다. 블록 원문 저장은 `.json` 블록이면 JSON 문법을 검사해 거부한다.

앱 홈 상태(`GET/POST /home`), 라우팅 표(`GET/PUT /config/routes`), 앱 설정(`GET/PUT /config`),
프로젝트 설정(`GET/PUT /projects/{p}/config`)도 생성 클라이언트(`SetupApi`)로 부른다. 가짜 core는 설정
파일을 메모리에 두고, 올바른 YAML 매핑인지와 프로젝트 설정의 최상위 키(`track`, `runs`, `policy`,
`publish`, `viewers`)만 검사한다. `SettingsScreenshotTest`는 거부된 프로젝트 설정을
`settings-config.png`로 남긴다.

## 설정 화면

프로젝트 열 위의 톱니바퀴로 연다. core 주소, 앱 설정(앱 홈 `config.yaml`), 프로젝트 설정(고른 프로젝트의
`.madang/config.yaml`), 라우팅 표, 실행기, 언어가 있다. yaml 파일은 원문 그대로 줄 번호 편집기로 고치고,
저장하면 core가 스키마를 검사한다. 거부되면 원문은 그대로 두고 문제가 있는 줄 옆과 편집기 아래에 이유를
보인다. 프로젝트 설정은 처음에 메인 화면에서 고른 프로젝트를 열고, 위의 프로젝트 칩으로 바꾼다. 기억(md)은
설정 화면이 아니라 사이드바 메모리 탭에서 고친다.

## core API 클라이언트 생성

컴파일 전에 `:shared:openApiGenerate`가 `../core/openapi.yaml`에서 Kotlin 모델·클라이언트를
`shared/build/generated/openapi/`에 만들고 `commonMain`에 포함한다(패키지 `madang.api`,
Ktor + kotlinx-serialization). 계약은 이 파일 하나이며 앱에 손으로 쓴 API 모델은 없다.

이벤트(`Event`)는 생성기가 oneOf를 제대로 만들지 못하므로 `EventEnvelope`로 `type`을 먼저 읽고
구체 이벤트(`RunProgressEvent` 등)로 다시 해석한다. 생성된 `EventsApi`는 쓰지 않는다.

다른 명세 파일로 생성하려면:

```sh
./gradlew :shared:openApiGenerate -Pmadang.openapiSpec=/path/to/openapi.yaml
```

## 패키징

`compose.desktop.application`에 `Dmg`(macOS), `Msi`(Windows)가 설정되어 있다. 배포물에는 core를
PyInstaller로 묶은 실행 파일을 싣는다. 먼저 저장소 루트에서 core를 만들고 나서 패키징한다.

```sh
bash scripts/build-core.sh       # 저장소 루트에서. 결과: core/dist/madang-core/
./gradlew :desktop:packageDmg    # macOS. 결과: desktop/build/compose/binaries/main/dmg/
./gradlew :desktop:packageMsi    # Windows
```

- core는 onedir 번들(`madang-core/madang` + `_internal/`)이다. 한 파일 번들과 달리 실행할 때마다
  임시 폴더에 풀지 않아 시작이 빠르고, 앱 서명 때 안의 바이너리를 그대로 서명할 수 있다. tiktoken
  인코딩과 렌더러·뷰어 템플릿, 의존성의 라이선스 원문이 번들 안에 있다.
- 빌드가 `THIRD_PARTY_NOTICES.md`(저장소 루트)와 core 번들을 앱 리소스 폴더(`Contents/app/resources/`)에
  싣는다. 패키지된 앱은 설정에 core 실행 파일이 없으면 이 동봉 core로 `madang serve`를 띄운다.
  동봉 core는 자기 폴더를 PATH 앞에 두어 에이전트가 부르는 `madang`도 같은 실행 파일이 된다.
- core 번들이 없으면 패키징 작업은 실패한다. 개발 실행(`:desktop:run`)은 번들 없이도 된다.
- 브라우저·문서 탭 엔진(KCEF의 Chromium 번들)은 dmg에 넣지 않는다. 처음 열 때 앱 설정 폴더의
  `kcef-bundle/`에 내려받는다.
- 서명·공증은 하지 않는다. 아이콘은 흰색 자리표시 아이콘(`desktop/icons/`)이다.
- Finder로 연 앱은 셸의 PATH를 받지 않는다. `claude`가 `~/.local/bin`처럼 기본 PATH 밖에 있으면
  앱 홈 `config.yaml`의 `runners.claude.bin`에 절대 경로를 적거나, 터미널에서
  `<경로>/Madang.app/Contents/MacOS/Madang`으로 띄운다.
