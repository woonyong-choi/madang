# madang-app

Madang 데스크톱 앱. Kotlin Multiplatform + Compose Multiplatform.

지금 타깃은 desktop(JVM: macOS, Windows)이다. Android·iOS는 이후에 추가한다.

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
  앱 홈) → 첫 프로젝트 폴더 고르기(`POST /projects`) → claude 확인 순서다. claude 확인은
  `claude auth status` 출력의 로그인 여부와 방식만 본다. 로그인은 터미널에서 직접 하고, 로그인하지
  않았어도 시작할 수 있다.

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
7일·지난 30일·월별로 묶는다. 필터는 상태와 태그로 건다. 본문의 router 메시지와 run 카드, 지난 대화의
메시지는 한 줄로 접히며 클릭하거나 "모두 펼치기"로 펼친다. doc 블록은 Compose 마크다운으로 그리고,
mermaid는 코드 블록으로 보인다.

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

- 더블클릭 = 열기, 항상. 첫 탭 "페이지"는 블록 흐름이며 닫을 수 없다. 흐름에서 블록이나 run 카드를
  더블클릭하면 그 종류의 탭이 열리고, 이미 열려 있으면 그 탭으로 간다. doc·data·view 블록은 블록 파일의
  확장자, site 블록은 `url`, code 블록은 `path`(core가 알려 준 작업 폴더 기준, `GET /projects/{p}/git/status`의
  `folder`)를 연다. term 블록은 터미널 탭이 생길 때까지 열리지 않는다. run 탭과 페이지 탭은 문서 탭이다.
- 탭 안 오른쪽 서랍(접을 수 있음): 문서는 미리보기/원본, 데이터는 표/트리/원문, run은 입력 구성·사용량·바뀐
  파일·이벤트 로그(`GET /pages/{p}/runs/{n}/events`). run 탭 본문에는 그 run을 일으킨 요청과 run이
  남긴 메시지가 보인다.
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
  한글처럼 입력기가 글자를 조합하는 중의 Enter는 조합 확정이라 보내지 않는다. 첫 단어가 `de`처럼 종류 이름의
  앞부분이면 `design:` 같은 접두어 후보가 뜨고 Tab이나 클릭으로 채운다. 입력을 멈추고 300ms 뒤
  `GET /pages/{p}/preview-input`으로 다음 호출의 입력 토큰과 도구/모델을 받아 오른쪽에 보인다.
- 보낸 메시지는 core 응답 전에 본문 끝에 흐리게 붙고, core 페이지에 같은 메시지 블록이 생기면
  그 블록으로 바뀐다. 보내기에 실패하면 빠지고 입력창에 문장이 되돌아온다.
- 오른쪽 사이드바(페이지 제목 옆 "메모리" 또는 M): 지금 · 파일 · 메모리 · git · 포트 · 기록 탭 자리가 있고,
  지금은 메모리 탭만 내용이 있다. 메모리 탭은 Profile / Brief / Ledger를 언제나 이 순서로 위에서 아래로
  보인다. 층마다 머리부는 최상위 키별 입력칸(값은 `키:` 뒤의 원문, 고친 키의 줄만 바뀐다), 본문은 원문 그대로
  보인다(문서 렌더러가 붙기 전까지). "원문"을 켜면 파일 전체를 줄 번호 편집기로 고친다. 저장은 층마다 하고,
  core 검사기가 거부하면 문제를 그 키 입력칸 아래·본문 아래·원문 편집기의 줄 옆에 붙인다.
- 미등록 파일: `page.unknown_files` 이벤트가 오면 제목 아래 노란 띠가 뜬다. 띠를 누르면 목록이
  열리고 파일마다 산출물로 / 유지 / 삭제를 고른다.
- 사람 결정: `flow.waiting` 이벤트가 오면 페이지 위에 질문과 선택지 카드가 뜬다. 고르면 답을 보내고
  flow가 다시 돌면(`run.started`) 사라진다.
- 최근 삭제: 프로젝트 오른쪽 클릭 메뉴에서 연다. 등록한 모든 프로젝트의 `.madang/trash/`에 옮겨 둔
  페이지·블록을 최신순으로 보고 복구한다.
- 시작 화면에서 core에 연결하지 못하면 그 자리에서 core 주소를 고쳐 다시 연결할 수 있다.

앱은 앱 홈과 프로젝트의 `.madang/` 파일을 읽거나 쓰지 않는다(`core.port` 읽기만 예외). 작업 폴더 파일은
파일 탭(코드 보기·데이터)에서 읽기만 한다. 앱이 쓰는 파일은 앱 설정 `settings.json`과 브라우저 엔진 번들·캐시다(macOS `~/Library/Application Support/Madang`, Windows `%APPDATA%\Madang`,
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

## core 연결

`./gradlew :desktop:run`은 떠 있는 core가 없으면 `uv run --project ../core madang serve`로
core를 띄운다. 설정 화면의 "core 실행 파일"을 지정하면 `<파일> serve`를 쓴다. 실패하면 시작
화면에 원인과 "다시 시도"가 보인다.

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
문장에 "결정"이 들어 있으면 도중에 `flow.waiting`으로 선택지를 묻고, 답하면 마저 끝낸다. 메모리
저장은 ledger.md의 머리부 필수 키·status 값·필수 절·토큰 상한을 검사한다. 지운 페이지는 최근
삭제에서 되살릴 수 있다.

`./gradlew :desktop:test`는 이 픽스처로 메인 화면을 화면 밖에서 그려
`desktop/build/screenshots/`에 `wide.png`(3열), `narrow.png`(2열), `page.png`(1열)를 남긴다.
메시지를 보내 run 카드가 붙는 과정(`message-running.png`, `message-done.png`)과 사람 결정 카드·메모리
검사 오류(`decision-memory.png`), 메모리 탭의 세 층과 머리부 폼 검사 오류(`memory-tab.png`), 데이터 탭의 표
(`tabs-data.png`), 디프 탭(`tabs-diff.png`), 엔진을 처음 내려받는 브라우저 탭(`tabs-browser.png`)도 남긴다.
픽스처의 `git/<프로젝트 id>.diff`가 그 프로젝트의 작업 트리 diff이고, 그 파일이 없는 프로젝트는 git 저장소가
아니다. 블록 원문 저장은 `.json` 블록이면 JSON 문법을 검사해 거부한다.

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

`compose.desktop.application`에 `Dmg`(macOS), `Msi`(Windows)가 설정되어 있다.

```sh
./gradlew :desktop:packageDmg    # macOS
./gradlew :desktop:packageMsi    # Windows
```
