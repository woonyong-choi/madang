# Madang: 빌드 오케스트레이션 (오너 에이전트)

상태: 초안 (AI 작성, 미승인)
작성: 2026-09-24
목적: Phase A를 사람 개입 최소로 완료한다. 사람은 오너 창에서 보고를 읽고, 되돌릴 수 없는 결정에만 답한다.

## 1. 구조

```
사용자  ──(터미널 채팅)──►  오너 (tmux pane "owner", Claude Code)
                              │ tmux split-window / send-keys / capture-pane
                              ├─► 빌더 pane (codex exec 또는 claude -p, 비대화형)
                              ├─► 빌더 pane
                              └─► 리뷰어 pane
                              ▲
                              └── ops/reports/WP-xx.md (완료 보고, 고정 양식)
```

- 오너는 대화형 Claude Code 세션 하나다. 사용자는 이 pane에서 오너와 채팅한다.
- 빌더와 리뷰어는 **비대화형 새 세션**(`codex exec`, `claude -p`)이다. 작업 하나가 끝나면 프로세스가 끝난다. 세션을 이어 쓰지 않는다(원칙 6). 맥락은 `ops/tasks/WP-xx.md`(과업 명세)와 `ops/reports/WP-xx.md`(보고)로만 이어진다.
- 오너는 루프를 돈다: 보드 읽기 → 준비된 과업 배정 → 감시 → 보고 수신 → 리뷰 배정 → 통합 → 보드 갱신 → 반복. 모든 과업이 done이면 종료 보고.

## 2. 오너 선정 기준과 결정

| 기준 | 필요 | 이유 |
|---|---|---|
| 장기 판단 | 높음 | 수십 개 과업의 의존과 순서, 막힘의 원인 판단 |
| 도구 조작 | tmux, git, 파일 | pane 분할·감시·병합 |
| 서브에이전트 제어 | 필요 | 빌더·리뷰어 기동과 회수 |
| 확인 질문 억제 | 필요 | 사람이 자리에 없어도 진행 |
| 비용 | 중간 | 오너 자체는 코드를 거의 안 쓴다. 입력이 크고 출력은 짧다 |

**결정: 오너 = Claude Code, `claude-opus-5-5`, effort `high`, 권한 bypass(전역 설정).** Claude Code는 훅·서브에이전트·tmux 조작에 검증된 도구이고, Opus 5.5는 장기 판단과 비용의 균형점이다. Fable은 오너가 막혔을 때 오너가 스스로 한 번 상담하는 용도로만 쓴다(`claude -p --model claude-fable-5-1`).

역할별 모델(라우팅 표 준용):

| 역할 | 1차 | 승격 | 용도 |
|---|---|---|---|
| builder-core | codex / gpt-6-sol / medium | claude / opus-5-5 / medium | Python core |
| builder-app | codex / gpt-6-sol / medium | claude / opus-5-5 / high | Kotlin·Compose. KMP 설정 문제는 승격이 잦을 수 있다 |
| builder-web | codex / gpt-6-sol / medium | claude / opus-5-5 | templates, madang.js |
| reviewer | 구현한 쪽의 **반대** 도구, 주력 모델 | 상위 | 교차 리뷰 |
| fixer | codex / gpt-6-luna / high | codex / gpt-6-sol | 리뷰 지적 반영, 오타·소규모 |
| consultant | claude / fable-5-1 / high | 사람 | 오너가 2회 승격 후에도 막힐 때 1회 |

## 3. 파일 규약 (`ops/`)

```
ops/
├ README.md            이 폴더의 규칙
├ owner.md             오너 프롬프트 (기동 시 통째로 전달)
├ board.md             오너가 유지하는 보드. 과업 상태·담당·시도 횟수·다음 행동
├ roles/
│  ├ builder.md        빌더 프롬프트 템플릿 ({WP}, {SPEC} 치환)
│  ├ reviewer.md       리뷰어 프롬프트 템플릿
│  └ fixer.md
├ tasks/
│  └ WP-01.md …        과업 명세: 목표, 범위, 입력 문서, 완료 조건, 검증 명령, 금지 사항
├ reports/
│  └ WP-01.md …        보고: 고정 양식 (아래). 빌더·리뷰어가 종료 직전에 쓴다
└ log.md               오너의 한 줄 로그 (시각 | 행동 | 대상)
```

보고 양식 (`ops/reports/WP-xx.md`):

```markdown
# WP-xx 보고
role: builder-core | reviewer | fixer
tool: codex/gpt-6-sol
status: done | blocked | needs-review
branch: wp/01-core-skeleton
verify: uv run pytest -q → 12 passed   (실행한 명령과 실제 결과. 안 돌렸으면 "not run")

## 한 일
- (3~7줄)

## 남긴 것
- 파일 경로 목록

## 막힌 점 / 리뷰 지적
- (blocked 또는 needs-review일 때. 5줄 이내)

## 다음 사람에게
- (한 줄)
```

빌더는 브랜치 `wp/<id>-<slug>`에서 일하고 커밋한다. 오너만 `main`에 병합한다.

## 4. 오너 루프

```
시작
  1. docs/ai/*.md, ops/board.md, ops/tasks/*.md 읽기
  2. 보드가 비어 있으면 §5의 과업으로 채운다
반복 (모든 과업 done까지)
  3. 준비된 과업(의존 완료, 상태 todo) 중 최대 N개(기본 3) 선택
  4. 각 과업마다:
       tmux split-window로 pane 생성, 이름 = WP id
       역할 프롬프트를 치환해 파일로 저장 → 비대화형 실행:
         codex exec -m gpt-6-sol -c model_reasoning_effort=medium "$(cat prompt)"  또는
         claude -p --model claude-opus-5-5 --effort high "$(cat prompt)"
       종료 시 `touch ops/reports/WP-xx.done` 이 붙은 명령으로 실행
       보드: 상태 running, 담당, 시각
  5. 감시: 60초마다
       .done 파일 확인 → 보고 읽기
       capture-pane 마지막 30줄로 이상 징후(권한 프롬프트, 무한 반복, 오류 반복) 확인
       과업별 타임아웃(명세에 명시, 기본 40분) 초과 → 프로세스 종료, blocked 처리
  6. 보고 처리:
       done         → 리뷰 과업 생성(반대 도구), 상태 review
       needs-review → 같음
       blocked      → attempts+1. 2회 미만이면 같은 단계 재시도(막힌 점을 명세에 추가).
                      2회면 승격(상위 모델). 승격 후에도 blocked면 consultant 1회.
                      그래도 blocked면 사람 결정 카드(§6)
  7. 리뷰 보고 처리:
       pass → 오너가 main에 병합(fast-forward 또는 squash), 보드 done, pane 닫기
       fail → fixer 과업 생성(리뷰 지적을 명세로), 상태 fixing → 다시 리뷰
  8. 보드와 log.md 갱신. 사용자 pane에 한 줄 요약 출력
  9. 다음 준비된 과업으로
종료
  10. 모든 과업 done → Phase A 완료 기준 §7 점검 → 최종 보고 → 사용자 확인 대기
```

병렬 규칙: 같은 폴더(`core/`, `app/`, `templates/`)를 건드리는 과업은 동시에 하나만. 폴더가 다르면 병렬.

## 5. Phase A 과업 분해

의존은 "←". 담당은 1차 역할. 검증은 완료 조건에 포함된 실행 명령.

### A0. 바탕
- **WP-01 core 뼈대** (builder-core): `core/pyproject.toml`(uv, Python 3.12), 패키지 `madang`, `madang init`(앱 홈 생성 + git init + 기본 config), 설정 로딩. 검증: `uv run madang init --home /tmp/mh && test -d /tmp/mh/.git`.
- **WP-02 state 스키마·검사기** (builder-core) ← 01: `validate/state.py`(머리부 스키마, 본문 필수 절, 2,000토큰 상한, 경로 존재), `madang validate <page>`. 검증: 정상·오류 픽스처 각 3개로 pytest.
- **WP-03 실행기** (builder-core) ← 01: `runners/claude.py`, `runners/codex.py`, stream-json 파싱 → RunEvent 정규화, `runs/N.json`, 타임아웃. 검증: 각 CLI를 `echo`만 시키는 통합 테스트 1회(실제 구독 호출, 입력 5K 이하).
- **WP-04 madang CLI(에이전트용)** (builder-core) ← 02: `madang task/decide/artifact/promote/commit`. A0에서는 store 라이브러리를 직접 호출(A1에서 API로 교체). 검증: pytest.
- **WP-05 입력 조립 + 단발 실행** (builder-core) ← 03,04: `assemble()`(root/space/state/지시문/대상/요청, 토큰 추정), `madang run <page> --tool --model --effort "요청"`. 검증: 이력서 페이지 픽스처로 설계→작성→검토 3회 독립 실행, 각 입력 35K 이하, runs/ 3개, 앱 홈 커밋 3개. 결과를 보고에 수치로.

### A1. core 흐름
- **WP-06 LangGraph 흐름** (builder-core) ← 05: 노드·엣지(core 스펙 §4), `routes.yaml` 로딩, classify(접두+규칙), 승격 루프, 교차 리뷰, ask_human(interrupt), SQLite 체크포인터. 검증: 가짜 Runner로 done/blocked/review 세 경로 pytest.
- **WP-07 API + 이벤트** (builder-core) ← 06: FastAPI 라우터(core 스펙 §7), WebSocket 이벤트, `openapi.yaml` 생성·커밋, 미등록 파일 감지, trash/restore. 검증: httpx 테스트 + `openapi.yaml` 스키마 검증.
- **WP-08 CLI를 API 경유로 전환** (fixer) ← 07: `madang` 명령이 core API를 부르게. 검증: WP-04 테스트 통과.

### A2. 앱 뼈대
- **WP-09 KMP 뼈대** (builder-app): `app/` Gradle, Compose Multiplatform desktop 타깃, `shared`·`desktop` 모듈, Ktor 클라이언트, openapi 생성 설정. 검증: `./gradlew :desktop:run`으로 빈 창, `:shared:test` 통과. macOS만 필수, Windows는 CI 표시.
- **WP-10 core 연결·온보딩·설정** (builder-app) ← 09, 07: 시작 시 `core.port` 탐색, 없으면 기동, 온보딩(앱 홈, claude/codex 확인, 권한 규칙 제안), 설정 화면. 검증: 수동 시나리오 + 유닛.
- **WP-11 레이어 0 3열** (builder-app) ← 10: **Notebook Navigator 100%**(앱 스펙 §2.1 매핑표). 공간 열(계층, 아이콘·색, 태그 트리), 페이지 목록 카드(미리보기, 상태 칩, 고정, 정렬, hover 액션, 드래그 이동), 본문 블록(message·run·doc·data), 접기. 검증: 픽스처 앱 홈으로 스크린샷 3장 + 키보드 탐색 유닛.
- **WP-12 입력창·메모리·띠·결정 카드** (builder-app) ← 11: 입력창(대상 표시, preview-input 토큰), 메모리 패널(3층 편집, 검사 오류 인라인), 미등록 파일 띠, 사람 결정 카드(flow.waiting), 최근 삭제. 검증: 이벤트 모의 테스트.

### A3. 뷰와 편집
- **WP-13 템플릿 런타임** (builder-web): `templates/_runtime/madang.js`(render, data-bind/each/attr, overlay, path 역추적, 선택 하이라이트, 브리지), 내장 4개(table, decisions, tasks, resume)의 template.yaml/page.html/schema/sample/theme. 검증: 헤드리스 브라우저(playwright)로 렌더·선택 테스트.
- **WP-14 뷰 블록·레이어 1** (builder-app) ← 12, 13: KCEF WebView actual, 본문 축소 렌더, 레이어 1(상단 탭, 연결 패널, 끌어다 놓기, 프리셋, 원본, 승격), decisions·tasks 뷰 자동 생성. 검증: 스크린샷 + 바인딩 PATCH 유닛.
- **WP-15 보기/편집·레이어 2** (builder-app) ← 14: 모드 토글, 요소 선택, 패널 직접 수정 → 데이터 저장, 선택 요소만 담는 요청(`target.elements`). core 측 조립 확인. 검증: "이 섹션을 2단으로" 시나리오의 조립 입력에 페이지 전체가 없고 조각만 있음을 테스트.

### A4. 패키징
- **WP-16 core 바이너리·앱 패키징** (builder-app) ← 15, 08: PyInstaller core, `packageDmg`, `packageMsi`(Windows는 CI), 앱이 동봉 core를 띄움. 검증: dmg 설치 후 시작 화면까지.
- **WP-17 권한 마법사·문서** (fixer) ← 16: 온보딩의 권한 규칙 추가(사용자 승인), README 사용법. 검증: 수동.
- **WP-18 수용 점검** (reviewer, claude/opus-5-5) ← 17: §7 기준 자동화 가능한 항목을 스크립트로, 나머지를 체크리스트로 `ops/reports/acceptance.md`에.

리뷰 과업은 각 WP 완료 시 오너가 `WP-xx-R`로 자동 생성한다. 위 목록에 적지 않는다.

## 6. 사람 결정 지점

오너는 다음에만 사용자에게 묻는다(오너 pane에 카드 형식으로 출력하고 대기). 나머지는 합리적 가정으로 진행하고 보드에 가정을 적는다.

1. 외부 계정·결제·삭제처럼 되돌릴 수 없는 행동(앱 홈 원격 저장소 생성, GitHub 설정 변경, 패키지 서명).
2. consultant까지 거친 뒤에도 blocked인 과업.
3. 설계 문서와 충돌하는 구현이 불가피할 때(예: KCEF가 특정 환경에서 불가). 이때 오너는 대안과 ADR 초안을 함께 제시한다.
4. Phase A 완료 기준 점검 결과 보고.

## 7. 완료 기준 (Phase A)

로드맵 §Phase A와 같다. 오너는 종료 전 다음을 실제로 수행해 보고한다.

1. `madang run`으로 이력서 페이지 3회 독립 실행: 각 입력 ≤ 35K, 세션 미재사용.
2. 앱을 dmg로 설치해 띄우고, 3열에서 새 페이지를 만들고, 메시지 하나가 라우터→실행→검사→판정→커밋을 타는 것을 이벤트 로그로 확인.
3. resume 템플릿에 덮어쓰기 3벌 연결, 프리셋 전환 즉시 반영.
4. 편집 모드 요소 선택 요청의 조립 입력에 조각만 포함.
5. 2주 사용 기준은 사람이 판정. 오너는 체크리스트만 남긴다.

## 8. 커밋·브랜치 규칙

- 빌더: `wp/<id>-<slug>` 브랜치, commit 스킬 형식, AI 흔적 없음(ADR D19). 자기 범위 파일만.
- 오너: 리뷰 pass 후 `main`에 squash merge. 메시지는 WP 제목을 명령형으로. 하루 1회 이상 push.
- 절대 금지: force push(main), `--no-verify`, 작성자 변경.

## 9. 비용·시간 가드

- 과업당 타임아웃: 명세에 명시(기본 40분). 초과 시 blocked.
- 과업당 시도 상한 2, 승격 1, consultant 1. 총 4회 실행 후에도 안 되면 사람.
- 동시 pane 최대 3. 같은 최상위 폴더는 동시 1.
- 오너는 빌더 pane의 전체 출력을 읽지 않는다. 보고 파일과 마지막 30줄만.
- 오너 자신의 컨텍스트가 커지면 `/compact`를 쓰되, 보드와 로그가 진실이므로 잃는 것이 없어야 한다.

## 10. 사용자가 보는 것

- 오너 pane: 루프마다 한 줄 요약(`[WP-03] running codex/gpt-6-sol 12m`, `[WP-02] review pass → merged`).
- `ops/board.md`: 전체 현황 표.
- 다른 pane: 각 빌더의 실시간 출력(원하면 본다, 안 봐도 된다).
- 사용자가 오너 pane에 말하면 오너는 루프를 잠시 멈추고 답한 뒤 재개한다.
