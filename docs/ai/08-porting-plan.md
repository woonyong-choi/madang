> **v2 주의(2026-09-24):** 이 문서는 10-spec-v2.md 이전 초안이다. 충돌하는 부분은 10-spec-v2.md와 05-decisions.md D26~D33이 우선한다.

# Madang: 독립 앱 방향 확정과 Orca·Notebook Navigator 이식 계획

상태: 초안 (AI 작성, 미승인)
작성: 2026-09-24

## 1. 확정

- **Madang은 독립 앱이다.** KMP + Compose Multiplatform 데스크톱(macOS·Windows), 이후 Android·iOS. Orca 플러그인이 아니고, Orca 안에서 여는 웹 화면도 아니다.
- **Orca가 잘하는 것은 Orca 코드로 만든다.** Orca는 MIT라 코드를 가져올 수 있다. 터미널·브라우저·상태 감지·사용량·주석 전송을 처음부터 설계하지 않고 Orca 구현을 읽고 옮긴다. 저장소에 `THIRD_PARTY_NOTICES.md`를 두고 Orca(MIT, Stably AI) 고지를 유지한다.
- **Notebook Navigator는 설계 참고만 한다.** GPL-3.0이라 코드를 복사하면 Madang이 GPL이 된다. 화면 구조, 조작, 설정 항목을 그대로 따르되 Kotlin으로 새로 쓴다.
- **Orca에 없는 엣지가 상품이다.** 페이지가 기록, 메모리가 파일, 호출별 입력 구성, 구독 간 자동 라우팅·대체, 살아 있는 뷰와 게시, 세션 없는 실행. 이 여섯이 core에 있고, 화면은 이를 드러내는 일을 한다.

## 2. 구조 단순화 (ADR D23)

앱 홈 저장소, 승격, 페이지가 worktree를 소유하는 별도 규칙을 버린다.

- **프로젝트 = 로컬 폴더(보통 git 저장소).** 왼쪽 목록의 최상위. Orca의 "프로젝트" 자리.
- **페이지 = `<project>/.madang/pages/<id>/`.** 기록이 프로젝트와 함께 간다. 커밋할지 `.gitignore`할지는 사용자가 정한다(기본: 커밋 안 함, 원하면 켬).
- **전역은 `~/.madang/`에 설정과 root.md만.** 프로젝트 메모리는 `<project>/.madang/project.md`.
- **worktree는 Orca 방식 그대로.** 코딩 페이지를 시작하면 브랜치·worktree를 만들고 그 안에서 에이전트와 터미널이 돈다. 페이지 폴더는 메인 체크아웃의 `.madang/`에 있어 worktree를 지워도 기록은 남는다. 이것이 규칙의 전부다.
- **비코딩 작업(이력서 등)도 폴더 하나다.** git이 없으면 worktree만 없다.
- Obsidian으로 `.madang/`을 열면 그냥 마크다운이다(위키링크·머리부 호환 유지).

## 3. 화면 (ADR D24)

Orca 배치를 채택하고, 왼쪽 목록의 단위만 페이지로 바꾼다.

```
┌──────────┬──────────────────────────────────────┬───────────────┐
│ 프로젝트   │ [페이지] [base.json] [터미널] [사이트]   │ 오른쪽 사이드바  │
│ └ 페이지   │                                      │ 탭: 지금 / 메모리│
│   (상태    │   활성 탭 (탭 끌기로 분할)              │  / 파일 / 기록  │
│    글리프, │                                      │  / 산출물 / 포트 │
│    브랜치) │                                      │               │
│          ├──────────────────────────────────────┤               │
│          │ [활성 탭]에게…                 [보내기] │               │
└──────────┴──────────────────────────────────────┴───────────────┘
```

- 왼쪽: Orca의 프로젝트 → worktree 트리 자리에 프로젝트 → 페이지. 카드 내용은 Notebook Navigator식(미리보기, 상태 글리프, 굵게, 고정, 정렬, hover 액션, 드래그). 좁으면 2열·1열.
- 가운데: 탭·분할(Orca 모델). 첫 탭은 "페이지". 블록 클릭 → 탭.
- 오른쪽 사이드바 탭: **지금**(모든 프로젝트의 진행 중 실행, 진행 로그, 사용량 막대), **메모리**(root/project/state 편집, 이번 호출에 읽힌 파일 칩), **파일**(worktree 파일 트리, git 상태 색), **기록**(에이전트 세션 기록. Orca의 Agent Session History 자리. 우리는 세션이 아니라 실행 목록), **산출물**(페이지가 만든 파일, 미등록 파일), **포트**(Phase C).
- "파일 트리 없음" 원칙은 철회한다. 오른쪽 탭 하나로 둔다. 다만 파일은 편집하지 않는다(외부 편집기로 열기).

## 4. Orca에서 코드로 가져올 것 (모듈별)

Orca 저장소 `src/`를 읽고 옮긴다. 대상 언어가 다르므로 "로직과 형식"을 옮기고 UI는 Compose로 다시 쓴다. WebView(KCEF) 안에서 도는 것은 JS 그대로 쓸 수 있다.

| # | Orca 모듈(추정 위치) | 가져올 것 | Madang 위치 | 언어 | 단계 |
|---|---|---|---|---|---|
| 1 | 에이전트 상태 감지: OSC 제목 파서 + 훅 서버 | 상태 어휘(working/needs-you/done/blocked/idle), Claude·Codex 훅 페이로드 해석, 제목 문자열 패턴 | core `procs/state.py` | Python으로 이식 | C |
| 2 | 사용량 추적: `~/.claude`·`~/.codex` 디스크 상태 파서, 창(5h/일/주/Fable 주) 계산, 80% 경고, 로컬 가격표 | 파서와 계산 그대로 | core `usage/` + `GET /usage` | Python으로 이식 | **v0.1(WP-25)** |
| 3 | 터미널: xterm.js + addon(webgl, fit, search, serialize, ligatures, web-links) 구성, kitty 키보드 프로토콜, 스크롤백 직렬화 | WebView 안에 xterm 번들 + Orca의 설정값 | app `desktop` WebView, core PTY | JS 그대로 | C |
| 4 | PTY 데몬: 앱과 분리된 프로세스가 PTY 소유, warm-reattach, Windows 자기 복사 | 설계 그대로 | core `procs/daemon.py` (node-pty 대신 Python pty/ptyprocess 또는 별도 작은 Node 데몬) | 이식 | C |
| 5 | 브라우저: 프로필(스토리지 파티션·UA·뷰포트), CDP 뷰포트 에뮬레이션, 쿠키 가져오기 | KCEF 대응 API로 | app `desktop` | Kotlin 재작성 | C |
| 6 | Design Mode 주입 스크립트: 요소 하이라이트, outer HTML+주변, 계산된 CSS, 스크린샷 자르기, 소스맵 파일·줄, 주석 트레이 | 주입 JS 그대로 (우리 data-bind 경로 추가) | `templates/_runtime/madang.js`와 사이트 탭 | JS 그대로 | A3·C |
| 7 | 디프 뷰어·주석: 줄 고정 댓글, 편집 후 추적, 프롬프트 합성, Resolve, 스테이지 단위 | 로직 | app code 탭 + core 조립 | Kotlin 재작성 | C |
| 8 | Jump 팔레트 순위 규칙: needs-you → done → idle, 제목·PR 매칭, 없으면 생성 | 규칙 | app Cmd-K | Kotlin | A2 |
| 9 | 알림: 완료 시 시스템 알림·소리·칩, 헤더 종, Dock 배지, 소리 파일 형식 | 규칙 | app | Kotlin | **v0.1** |
| 10 | 세션 복원: worktree·탭 배치·터미널 버퍼·마지막 화면 복원, 재부팅 후 배치만 | 규칙 | app 상태 저장 | Kotlin | C |
| 11 | Orca CLI 설계: `--json` 일관, 스킬 스텁으로 에이전트가 사용법 학습, `worktree set --comment --workspace-status` | 명령 설계 | `madang` CLI | Python | A0~ |
| 12 | 통합: GitHub OAuth/gh, Linear 토큰, 이슈→페이지 생성, PR 탭 | 흐름 | app·core | Phase B~C | B |
| 13 | 원격: `orca serve` 와이어 프로토콜(capability negotiation), 페어링 코드, 릴레이 | 설계 | core 원격 모드 | Phase C(모바일) | C |
| 14 | 벤치: idle-cpu, startup, cold-park-reveal | 측정 항목 | scripts | A4 | A4 |

가져오지 않는 것: Electron 전체, Monaco 편집기, Tiptap 편집기(문서 블록은 우리 md 렌더), 27종 에이전트 어댑터(Claude·Codex 둘만), 텔레메트리, 동면, `--resume` 세션 재개.

## 5. Notebook Navigator에서 설계로 가져올 것 (코드 금지)

앱 스펙 §2.1 매핑표를 유지한다. 추가로 설정 항목을 그대로 옮긴다: 미리보기 줄 수(1~5), 썸네일, 날짜 그룹(오늘/어제/기간/월/연), 속성 그룹, 작업 진행 표시, 고정, 폴더별 정렬, 포커스 모드, 선택 이력(뒤로/앞으로), VIM식 키 옵션, 단일/이중 pane 전환 애니메이션, 가로/세로 분할 방향, 21개 언어 중 ko·en·ja·zh.

## 6. Orca에 없는 엣지 (상품)

| 엣지 | 사용자가 보는 것 | Orca |
|---|---|---|
| 페이지가 기록 | 3주 전 작업의 요청·결정·산출물·읽은 파일을 다시 연다. 브랜치를 지워도 남는다 | worktree 지우면 사라짐 |
| 메모리가 파일 | 에이전트가 매 호출 읽는 3층 메모리를 오른쪽 탭에서 편집. "이번에 읽은 파일" 칩 | "메모리는 에이전트 것" |
| 호출별 입력 구성 | 보내기 전 토큰 합계, 보낸 뒤 부분별 구성 | 구독 한도만 |
| 자동 라우팅·대체 | 모델을 고르지 않는다. 막히면 승격, 로그인 없으면 반대 도구 | 사람이 고름, 수동 fan-out |
| 세션 없는 실행 | 호출당 입력이 고정 크기. 비용 예측 가능 | 세션 누적 |
| 살아 있는 뷰·게시 | 템플릿+데이터, 프리셋, 내 도메인 게시 | md 공유 링크만 |
| 파일 호환 | `.madang/`을 Obsidian·에디터로 그대로 연다 | 앱 내부 상태 |

## 7. v0.1에 대한 영향

- 저장 구조를 `<project>/.madang/`로 바꾼다(core store 수정, 앱 홈 초기화·승격 제거). 지금이 가장 싸다.
- 오른쪽 "지금" 패널은 4번째 열이 아니라 **오른쪽 사이드바의 탭**이 된다. 같은 사이드바에 메모리·기록 탭. WP-12의 메모리 패널을 이 사이드바로 옮긴다.
- 사용량은 Orca 파서를 Python으로 옮겨 core에서 계산한다.
- 그 외 v0.1 범위는 그대로.
