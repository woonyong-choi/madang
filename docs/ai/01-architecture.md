> **v2 주의(2026-09-24):** 이 문서는 10-spec-v2.md 이전 초안이다. 충돌하는 부분은 10-spec-v2.md와 05-decisions.md D26~D33이 우선한다.

# Madang: 아키텍처

상태: 초안 (AI 작성, 미승인)
작성: 2026-09-24

## 1. 전체 그림

Madang은 두 개의 프로세스와 하나의 폴더로 이루어진다.

```
┌───────────────────────────────────────────────────────────────┐
│  madang-app  (Kotlin Multiplatform + Compose Multiplatform)     │
│  macOS · Windows · (Android · iOS)                              │
│  - 3열 화면, 레이어 0/1/2, 입력창                                 │
│  - WebView: md·mermaid·템플릿 렌더링, 요소 선택 브리지            │
│  - 파일을 직접 쓰지 않는다. 모든 변경은 core API로               │
└───────────────┬───────────────────────────────────────────────┘
                │ HTTP (REST, OpenAPI) + WebSocket (이벤트)
                │ localhost:7470  (원격이면 LAN/릴레이)
┌───────────────▼───────────────────────────────────────────────┐
│  madang-core  (Python 3.12, FastAPI, LangGraph)                 │
│  - 흐름 엔진: 라우터 → 조립 → 실행 → 검사 → 판정 → 커밋           │
│  - 실행기: claude -p / codex exec 를 새 세션으로 subprocess 호출  │
│  - 검사기: state.md 스키마, 상한, 경로, 민감정보                  │
│  - 단일 작성자: 앱 홈 폴더의 모든 파일 쓰기와 git 커밋             │
│  - madang CLI: 에이전트가 부르는 부작용 명령 (같은 패키지)         │
└───────────────┬───────────────────────────────────────────────┘
                │ 파일 읽기/쓰기, git
┌───────────────▼───────────────────────────────────────────────┐
│  앱 홈  ~/.madang/   (비공개 git 저장소)                          │
│  spaces/ · pages/ · templates/ · runs/ · config/                │
└───────────────────────────────────────────────────────────────┘
                │ cwd로 사용 (에이전트가 코드를 고치는 곳)
┌───────────────▼───────────────────────────────────────────────┐
│  코드 저장소  ~/workspace/<repo>/   (사용자 것, 공간에 연결)        │
│  Madang이 만드는 파일은 승격된 docs/ 뿐                            │
└───────────────────────────────────────────────────────────────┘
```

## 2. 왜 두 언어인가

| 부분 | 언어 | 이유 |
|---|---|---|
| core | Python | LangGraph가 Python 네이티브. subprocess·파일·git·YAML 처리가 표준 라이브러리로 충분. 에이전트 CLI 자체가 프로세스라 core도 로컬 프로세스여야 한다 |
| app | Kotlin (KMP + Compose Multiplatform) | 사용자 선택. macOS·Windows 데스크톱을 한 코드로, 이후 Android·iOS로 확장. 데스크톱은 JVM 타깃 |
| 템플릿·렌더링 | HTML/JS | 모든 플랫폼의 WebView에서 같은 렌더러. 커뮤니티 템플릿이 웹 표준이어야 한다 |

두 언어의 경계는 **OpenAPI 계약** 하나다. `core/openapi.yaml`이 진실이고, Kotlin 클라이언트는 여기서 생성한다. 앱은 core의 내부 구조를 모르고, core는 앱의 화면을 모른다.

LangGraph를 JVM으로 옮기는 선택(LangGraph4j 등)은 하지 않는다. 이유: 공식 구현의 interrupt·체크포인터·스트리밍이 필요하고, core는 어차피 별도 프로세스라 언어가 달라도 비용이 없다.

## 3. 프로세스 경계와 책임

### madang-core

- **단일 작성자.** 앱 홈 폴더에 쓰는 프로세스는 core뿐이다. 앱은 API로 요청하고, 에이전트는 `madang` CLI로 요청하며, CLI는 core API를 부른다. 그래서 불변조건(블록 순서, 등록되지 않은 파일, 상한)이 한곳에서 지켜진다.
- **흐름 엔진.** LangGraph 그래프 하나가 "페이지에 메시지 하나"를 처리한다. 노드는 순수 함수이며 LLM을 직접 부르지 않는다(결정기 제외).
- **실행기(Runner).** 도구별 어댑터. 입력 조립 → 새 세션 subprocess → 스트림 이벤트 파싱 → 결과. 구독 CLI(로컬)와 API(서비스)는 같은 인터페이스의 다른 구현.
- **결정기(Decider).** 선택지와 상태를 받아 선택과 확신도를 돌려준다. 구현체: 규칙 → 경량 모델 → Jev. 확신이 낮으면 다음 구현체로.
- **검사기(Validator).** state.md 스키마, 토큰 상한, 경로 존재, 미등록 파일, 민감정보.
- **프로세스 관리자.** 터미널 블록의 셸 프로세스를 소유한다. 페이지가 닫혀도 산다.
- **이벤트.** 모든 상태 변화를 WebSocket으로 내보낸다. 앱은 폴링하지 않는다.

### madang-app

- 화면과 입력만. 파일 시스템에 손대지 않는다.
- 세 가지 렌더링: 네이티브(3열, 목록, 패널, 입력창), WebView(md, mermaid, 템플릿), WebView 브리지(요소 선택, 편집 모드).
- 앱은 core 없이는 동작하지 않는다. 시작 시 core를 찾고, 없으면 띄운다(데스크톱). 모바일은 데스크톱의 core에 붙는다.

### madang CLI (에이전트용)

- core와 같은 Python 패키지의 진입점. 에이전트가 Bash로 부른다.
- 하위 명령만 존재하며, 각 명령은 core API 하나에 대응한다. 권한 규칙에 `madang *`만 허용하면 에이전트의 모든 부작용이 core를 거친다.

## 4. 데이터 흐름: 메시지 하나의 일생

```
사용자 입력 "펄어비스용 요약문 다듬어줘"  (대상: 이력서 뷰 블록, 편집 모드, 요소 선택 1개)
   │
   ▼ POST /pages/{id}/messages  {text, target:{block, elements}}
[core] log.md에 메시지 블록 추가 → 이벤트 block.added
   │
   ▼ LangGraph 실행
classify   대상이 블록이면 종류 고정(small). 페이지 대상이면 결정기 호출
assemble   root.md + space.md + state.md + 공통 지시문 + 대상 블록 파일·연결 데이터 + 요청
           → 입력 토큰 수 계산 → 이벤트 run.assembled {tokens}
run        Runner(codex, gpt-6-luna, high).exec(cwd=코드저장소, prompt)
           스트림 이벤트를 run.progress로 중계
validate   state.md 검사 · git status 비교로 새 파일 → 미등록이면 page.unknown_files
           인계 테스트(4단계 이후)
judge      status: done | blocked | review
           blocked → tier+1, 다시 run (막힌 점 5줄만 전달)
           review  → 반대편 도구로 review 종류 run
           done    → 다음
commit     민감정보 검사 → 앱 홈 저장소 커밋 "[page] run 7 · codex/gpt-6-luna · +pearlabyss.json"
   │
   ▼ 이벤트 run.finished, page.updated
[app] 본문에 실행 기록 블록 추가, 뷰 블록 다시 그림 (데이터가 바뀌었으므로)
```

## 5. 모바일과 원격

- core는 모바일에서 돌지 않는다. 에이전트 CLI와 코드 저장소가 데스크톱에 있기 때문이다.
- 모바일 앱은 같은 KMP 코드로 빌드되며, 데스크톱 core에 붙는 클라이언트다. Phase C에서 LAN 직접 연결, Phase F에서 릴레이 서버.
- 그래서 앱은 처음부터 "core 주소"를 설정으로 가진다. 데스크톱의 기본값은 `localhost:7470`.

## 6. 서비스 실행기 (Phase F)

로컬 실행기(사용자 구독 CLI)와 서버 실행기(운영자 API 키)는 같은 Runner 인터페이스다. 그래프, 검사기, 앱은 어느 쪽인지 모른다. 서비스로 갈 때 바뀌는 것은 Runner 구현체와 앱 홈의 위치(서버)뿐이다. 두 실행기를 한 프로세스에서 섞지 않는다(약관).

## 7. 저장소 구조 (모노레포)

```
madang/
├ README.md
├ LICENSE                 MIT
├ docs/                   승인된 문서만 (사람이 옮김)
│  └ ai/                  AI 초안. 승인되면 docs/로 이동
│     ├ 00-vision.md
│     ├ 01-architecture.md
│     ├ 02-core-spec.md
│     ├ 03-app-spec.md
│     ├ 04-roadmap.md
│     ├ 05-decisions.md
│     └ reference/        조사·목업 HTML
├ core/                   Python 패키지 madang (core + CLI)
│  ├ pyproject.toml
│  ├ openapi.yaml         앱과의 계약 (진실)
│  └ madang/
│     ├ api/              FastAPI 라우터
│     ├ graph/            LangGraph 노드·그래프
│     ├ runners/          claude.py, codex.py, api_anthropic.py, api_openai.py
│     ├ deciders/         rules.py, light_model.py, jev.py
│     ├ store/            페이지 폴더 읽기·쓰기, git
│     ├ validate/         state 스키마, 민감정보
│     ├ procs/            터미널 프로세스 관리
│     └ cli.py            madang 명령
├ app/                    Kotlin Multiplatform
│  ├ settings.gradle.kts
│  ├ shared/              공용 UI·모델·API 클라이언트 (commonMain)
│  ├ desktop/             JVM 타깃 (macOS, Windows)
│  ├ android/
│  └ ios/
├ templates/              내장 템플릿 (HTML/JS + schema.json + sample.json)
│  ├ _runtime/            madang.js (렌더·바인딩·선택 브리지)
│  ├ table/
│  ├ decisions/
│  ├ tasks/
│  └ resume/
└ scripts/                빌드·릴리스
```

## 8. 기술 선택 요약

| 항목 | 선택 | 대안과 이유 |
|---|---|---|
| 앱 프레임워크 | Compose Multiplatform 1.8+ | Flutter는 Kotlin 아님. KMP는 사용자 스택 |
| 데스크톱 WebView | KCEF (Chromium Embedded) | JavaFX WebView는 최신 CSS·JS 지원이 약함. 크기(≈100MB)는 감수 |
| 모바일 WebView | Android WebView, iOS WKWebView | 플랫폼 기본 |
| HTTP 클라이언트 | Ktor (KMP) | OpenAPI 생성 클라이언트와 결합 |
| core 웹 프레임워크 | FastAPI + uvicorn | OpenAPI 자동 생성, WebSocket 지원 |
| 흐름 | LangGraph (Python) | interrupt, 체크포인터(SQLite), 스트리밍 |
| 체크포인터 | SQLite (`~/.madang/core.db`) | 그래프 실행 상태만. 문서는 파일이 진실 |
| md 렌더 | markdown-it + mermaid (WebView 내) | 플랫폼 간 동일 결과 |
| 템플릿 바인딩 | 자체 `data-bind` 규칙 + `madang.js` | 요소↔데이터 경로 1:1이 필요. 기존 템플릿 엔진은 역추적이 없음 |
| 앱 홈 저장소 | git (libgit2 대신 git CLI) | 사용자가 같은 도구로 열어볼 수 있어야 함 |
| 패키징 | 데스크톱: Compose `packageDmg`/`packageMsi` + core는 PyInstaller 바이너리 동봉 | 사용자가 Python을 설치하지 않아도 됨 |
| 포트 | 7470 | 충돌 시 자동 증가, 앱은 `~/.madang/core.port`로 찾음 |
