# Madang: core 스펙

상태: 초안 (AI 작성, 미승인)
작성: 2026-09-24
범위: Phase A 기준. 이후 단계의 항목은 "(Phase X)"로 표시.

## 1. 객체 모델

| 객체 | 정의 | 디스크 |
|---|---|---|
| Space | 페이지의 묶음. 코드 저장소 경로를 0개 또는 1개 가진다. 루트 공간은 항상 있다 | `spaces/<slug>/space.md` |
| Page | 하나의 작업이자 대화이자 문서 | `spaces/<slug>/pages/<id>/` |
| Block | 페이지 안의 단위. 종류: message, doc, data, view, code, term, site, run | 페이지 폴더 안의 파일 하나 (message는 `log.md`의 항목) |
| Template | 뷰 블록의 표현. 슬롯(스키마)과 렌더러 | `templates/<name>/` |
| Data | 슬롯에 들어가는 값. 파일 또는 API(Phase C) | `blocks/*.json`, `*.csv`, `*.source.yaml` |
| Binding | 뷰의 슬롯 ↔ 데이터 한 줄. 이름 붙인 묶음이 Preset | 뷰 블록 머리부 |
| Memory | 에이전트가 매 호출 읽는 문서 3층 | `root.md`, `space.md`, `state.md` |
| Run | 에이전트 호출 한 번의 기록 | `runs/<n>.json` |
| Process (Phase C) | 터미널 블록 뒤의 셸 | `procs/<id>.yaml` + 로그 |

ID 규칙: 페이지 `YYYY-MM-DD-<slug>`, 블록 `b<NN>` (페이지 안에서 증가, 재사용 없음), 실행 `<n>` (페이지 안에서 증가).

## 2. 앱 홈 디스크 구조

```
~/.madang/                       git 저장소 (비공개). core만 쓴다
├ config/
│  ├ madang.yaml                 전역 설정
│  ├ routes.yaml                 라우팅 표
│  ├ runners.yaml                도구·모델 목록과 실행 방법
│  └ secrets.yaml                API 키 등 (git 제외)
├ root.md                        메모리 1층
├ spaces/
│  └ <slug>/
│     ├ space.md                 메모리 2층 + 머리부(repo 경로, 설정)
│     ├ shared/                  공간 안 페이지들이 공유하는 데이터
│     └ pages/
│        └ <page-id>/
│           ├ page.md            머리부: 제목, 상태, blocks 순서
│           ├ state.md           메모리 3층
│           ├ log.md             대화 로그 (message 블록의 원본)
│           ├ blocks/            doc·data·view·code·term·site 파일
│           ├ runs/              실행 기록 JSON
│           └ scratch/           임시 (git 제외, 실행 후 정리)
├ templates/                     사용자 설치 템플릿 (내장은 앱 번들)
├ core.db                        LangGraph 체크포인터 (git 제외)
├ core.port                      현재 core 포트
└ .gitignore                     scratch/, secrets.yaml, core.db, core.port
```

## 3. 파일 형식

### 3.1 page.md

```markdown
---
id: 2026-09-24-resume
title: 이력서
kind: build            # 페이지의 기본 작업 종류 (라우터 힌트)
status: doing          # planning | doing | blocked | review | done
created: 2026-09-24T08:10:00+09:00
updated: 2026-09-24T09:40:00+09:00
pinned: false
tags: [지원]
blocks:                # 본문 순서. 진실은 이 목록이다
  - b01                # message는 log.md의 항목 id
  - b02
  - b05
---
사람이 쓰는 개요. 선택.
```

### 3.2 state.md (메모리 3층)

머리부는 기계가 읽고, 본문은 사람과 모델이 읽는다. **2,000토큰 상한** (초과 시 검사기가 거부하고 요약을 요구한다).

```markdown
---
status: review               # planning | doing | blocked | review | done
kind: build
tier: 1                      # 현재 승격 단계
attempts: 0                  # 같은 tier에서 실패 횟수
owner: codex/gpt-6-sol       # 마지막 실행 도구/모델
decisions:
  - id: D1
    topic: 갱신 경합 해결
    choice: refresh-lock
    options: [refresh-lock, sliding-session, client-retry]
    by: claude/opus-5-5
    run: 3
    state: confirmed         # proposed | confirmed | superseded | deferred
    supersedes: null
tasks:
  - {id: T1, title: 원인 분석, status: done}
  - {id: T2, title: 갱신 잠금, status: doing, due: 2026-09-26}
artifacts:                   # 이 페이지가 만든 파일. 코드 저장소 경로도 포함
  - blocks/b05-race-analysis.md
  - repo:src/session/lock.ts
---
## 목표
완료 조건을 포함한 한 문단.

## 결정 사항
확정된 것만. 바뀌면 덮어쓴다.

## 현재 상태
끝난 것과 위치.

## 다음 할 일
다음 실행이 바로 시작할 1~3개.

## 막힌 점
가설과 시도. 5줄 이내. 비어 있을 수 있다.

## 로그
2026-09-24 | codex/gpt-6-sol | run 4 | 갱신 잠금 구현, 통합 테스트 2개 실패
```

검사 규칙:
- 머리부 필수 키: status, kind, tier, attempts. 값은 열거형.
- decisions[].id 유일, options에 choice 포함, state 열거형.
- artifacts의 `blocks/` 경로는 페이지 폴더에 존재해야 하고, `repo:` 경로는 공간의 코드 저장소에 존재해야 한다.
- 본문 필수 절: 목표, 다음 할 일. 나머지는 선택.
- 전체 2,000토큰 이하 (tiktoken cl100k 기준으로 계산, 모델별 오차 감수).
- `status: done`은 마지막 run의 verify 결과가 성공일 때만 허용.

### 3.3 log.md (message 블록)

```markdown
<!-- b01 | 2026-09-24T08:11:02+09:00 | user | target=page -->
이력서 템플릿 만들어줘

<!-- b02 | 2026-09-24T08:11:03+09:00 | router | run=1 -->
kind=design conf=0.91 → claude/opus-5-5 high

<!-- b03 | 2026-09-24T08:14:40+09:00 | agent | run=1 -->
설계안 2개를 blocks/b05에 남겼습니다.

<!-- b06 | ... | user | target=b04 elements=work[1] mode=edit -->
펄어비스 경력을 맨 위로
```

주석 한 줄이 블록 머리부다. 본문은 그 다음부터 다음 주석 전까지.

### 3.4 블록 파일

| 종류 | 파일명 | 머리부 (YAML) |
|---|---|---|
| doc | `bNN-<slug>.md` | `type: doc`, `title`, `created_by: run N` |
| data | `bNN-<slug>.json` / `.csv` | 별도 사이드카 `bNN-<slug>.meta.yaml`: `type: data`, `schema` (선택), `created_by` |
| data (API, Phase C) | `bNN-<slug>.source.yaml` | `type: data`, `url`, `every`, `auth: secrets.<key>`, `cache` |
| view | `bNN-<slug>.view.md` | `type: view`, `template: resume@1`, `bindings: {slot: bNN}`, `presets: {name: {slot: bNN}}`, `active_preset`, `theme` |
| code (Phase C) | `bNN-<slug>.code.yaml` | `type: code`, `path: repo:src/x.ts`, `since_run: 4` |
| term (Phase C) | `bNN-<slug>.term.yaml` | `type: term`, `cmd`, `cwd`, `proc` |
| site (Phase C) | `bNN-<slug>.site.yaml` | `type: site`, `url`, `repo_bound: true` |
| run | `runs/N.json` | 별도 형식 (3.5) |

### 3.5 runs/N.json

```json
{
  "n": 7,
  "started": "2026-09-24T09:31:00+09:00",
  "finished": "2026-09-24T09:31:41+09:00",
  "trigger": {"message": "b06", "target": "b04", "elements": ["work[1]"], "mode": "edit"},
  "kind": "small", "tier": 1,
  "runner": "codex", "model": "gpt-6-luna", "effort": "high",
  "input": {
    "parts": {"system_est": 24600, "root": 110, "space": 1840, "state": 1320, "contract": 420, "target": 900, "request": 40},
    "total_est": 29230
  },
  "usage": {"input": 29104, "cached": 24310, "output": 612},
  "changed_files": ["blocks/b03-pearlabyss.json"],
  "unknown_files": [],
  "verify": {"cmd": null, "ok": null},
  "result_status": "done",
  "commit": "a1b2c3d",
  "events_log": "runs/7.events.jsonl"
}
```

### 3.6 config/routes.yaml

```yaml
kinds: [design, build, small, review, explore]
default_kind: build
prefix_override: true          # "design: …" 접두로 강제
rules:                          # 키워드 규칙 (결정기 1차)
  design: [설계, 아키텍처, 원인, 왜, 구조]
  review: [리뷰, 검토, 점검]
  small:  [오타, 이름, 한 줄, 문구]
  explore: [어디, 찾아, 설명해, 뭐야]
tiers:
  design:  [{runner: claude, model: claude-opus-5-5, effort: high},
            {runner: claude, model: claude-fable-5-1, effort: high}]
  build:   [{runner: codex,  model: gpt-6-sol, effort: medium},
            {runner: claude, model: claude-opus-5-5, effort: medium},
            {runner: claude, model: claude-fable-5-1, effort: high}]
  small:   [{runner: codex,  model: gpt-6-luna, effort: high},
            {runner: codex,  model: gpt-6-sol, effort: medium}]
  review:  [{runner: opposite, model: primary}]   # 구현한 쪽의 반대
  explore: [{runner: codex,  model: gpt-6-luna, effort: medium},
            {runner: claude, model: claude-sonnet-5, effort: medium}]
limits:
  max_runs_per_message: 6       # 승격·리뷰 포함
  blocked_after_failures: 2     # 같은 검증 연속 실패 횟수
decider:
  chain: [rules, light_model]   # Phase D: + jev
  min_confidence: 0.7
```

### 3.7 config/runners.yaml

```yaml
claude:
  bin: claude
  args: ["-p", "--output-format", "stream-json", "--verbose", "--model", "{model}", "--effort", "{effort}"]
  auth: subscription            # subscription | api
  cache_ttl: 1h
codex:
  bin: codex
  args: ["exec", "--json", "-m", "{model}", "-c", "model_reasoning_effort={effort}"]
  auth: subscription
```

## 4. 흐름 엔진 (LangGraph)

### 4.1 상태

그래프 상태에는 흐름 제어 값만 둔다. 문서 내용은 절대 상태에 넣지 않는다.

```python
class FlowState(TypedDict):
    space: str; page: str; message: str           # ids
    target: dict                                  # {block, elements, mode}
    kind: str; tier: int; attempts: int
    runner: str; model: str; effort: str
    run_n: int
    result_status: str                            # done | blocked | review
    runs_this_message: int
    pending_decision: dict | None                 # interrupt용
```

### 4.2 노드

| 노드 | 입력 | 하는 일 | 출력 |
|---|---|---|---|
| classify | message, target | 대상이 블록이면 kind 고정. 페이지면 접두 → 규칙 → 결정기 | kind |
| pick | kind, tier | routes.tiers[kind][tier] | runner, model, effort |
| assemble | 위 전부 | 입력 조립, 토큰 추정, `run.assembled` 이벤트 | prompt(파일로 저장) |
| run | prompt | Runner.exec, 스트림 중계, runs/N.json 초안 | usage |
| validate | run_n | state.md 검사, git status 비교, 미등록 파일 | ok / errors |
| repair | errors | 같은 세션 없음. 짧은 보정 요청을 같은 runner로 1회 | ok / fail |
| judge | state.status | done / blocked / review 분기. 한도 검사 | result_status |
| review_run | — | 반대편 runner로 review 종류 실행 (run 노드 재사용) | |
| commit | — | 민감정보 검사 → git commit | commit |
| ask_human | pending_decision | LangGraph interrupt. 앱에 선택지 표시 | 재개 값 |

### 4.3 엣지

```
classify → pick → assemble → run → validate
validate ─ok→ judge
validate ─errors→ repair ─ok→ judge
                         ─fail→ ask_human
judge ─done→ commit → END
judge ─review→ review_run → validate(리뷰 결과) → judge2 ─pass→ commit
                                                       ─fail→ (status를 doing으로, 다음 할 일에 지적 반영) → pick
judge ─blocked→ (tier+1, 한도 내) → pick
              ─(한도 초과)→ ask_human
```

체크포인터: SQLite. 앱이 꺼졌다 켜져도 `ask_human`에서 멈춘 흐름이 남아 있고, 앱이 답을 보내면 재개된다.

### 4.4 입력 조립 규칙 (assemble)

```
[Runner 자체 시스템 프롬프트 + 툴]     추정치만 (도구별 상수, runners.yaml에 기록)
[root.md]
[space.md]  (머리부 제외 본문)
[state.md]  (전체)
[공통 작업 지시문]  core 내장, 약 500 토큰
[대상]  target.block이 있으면: 그 블록 파일 + bindings의 데이터 파일 (각 4K 상한, 넘으면 앞부분 + "...")
        target.elements가 있으면: 해당 요소의 HTML 조각 + data path
[요청]  message 본문
```

승격 실행(tier > 1)일 때는 state.md의 "막힌 점"과 "다음 할 일"만 넣고, 로그 절은 뺀다.

### 4.5 공통 작업 지시문 (core 내장, 버전 관리)

```
너는 Madang 페이지 하나의 한 단계만 수행한다. 이전 세션은 없다.
1. state.md를 읽고 "다음 할 일"을 수행한다. 작업 폴더는 {repo}이다.
2. 새 문서는 {page}/blocks/ 에 만들고 state.md의 artifacts에 등록한다. 코드 저장소에 만든 파일도 repo: 접두로 등록한다.
3. 화면이 필요하면 HTML을 쓰지 말고 view 블록을 만든다: 템플릿 목록 {templates}. 데이터는 json으로.
4. 같은 검증이 {n}회 연속 실패하면 state.md의 status를 blocked로, "막힌 점"에 가설과 시도를 5줄 이내로 쓰고 즉시 종료한다.
5. 구현이 끝나면 status를 review로 쓴다. done은 쓰지 않는다(앱이 검증 후 쓴다).
6. 커밋·푸시·삭제·승격·결정 기록은 madang 명령으로만 한다: madang task, madang decide, madang commit, madang promote.
7. state.md는 2,000토큰을 넘기지 않는다. 넘으면 로그를 요약한다.
8. 확인 질문을 하지 않는다. 합리적 가정으로 진행하고 가정은 state.md 로그에 한 줄로 남긴다.
```

## 5. 실행기 (Runner)

```python
class Runner(Protocol):
    name: str
    def exec(self, *, cwd: Path, prompt: str, model: str, effort: str,
             on_event: Callable[[RunEvent], None]) -> RunResult: ...
```

RunEvent 종류(도구 무관으로 정규화): `text`, `tool_call {name, summary}`, `tool_result {summary}`, `file_changed {path}`, `usage`, `done`, `error`.

| 어댑터 | 호출 | 파싱 |
|---|---|---|
| claude | `claude -p --output-format stream-json --verbose --model M --effort E "<prompt>"` | 줄 단위 JSON. `assistant`/`tool_use`/`result` 이벤트 매핑 |
| codex | `codex exec --json -m M -c model_reasoning_effort=E "<prompt>"` | 줄 단위 JSON 이벤트 매핑 |
| api_anthropic (Phase F) | Messages API + 자체 툴 루프 | |
| api_openai (Phase F) | Responses API + 자체 툴 루프 | |

실행 조건:
- cwd는 공간의 코드 저장소. 없으면 페이지 폴더.
- 환경 변수로 `MADANG_PAGE`, `MADANG_CORE_URL`을 넘겨 `madang` CLI가 어느 페이지인지 안다.
- 타임아웃: kind별 (design 30분, build 20분, small 5분, review 10분, explore 5분). 초과 시 종료하고 blocked 처리.
- 권한: Claude `~/.claude/settings.json`에 `Bash(madang *)` allow, `Bash(git push *)`·`Bash(rm -rf *)` deny 권고. Codex `~/.codex/rules/`에 `prefix_rule(["madang"], "allow")`. 설치 마법사가 넣어 준다(사용자 승인 후).

## 6. madang CLI (에이전트용)

| 명령 | 하는 일 | core API |
|---|---|---|
| `madang task <id> --status S [--title T] [--due D]` | tasks 갱신 | PATCH /pages/{p}/state/tasks |
| `madang decide <id> --topic T --choice C --options a,b,c [--supersedes D0]` | 결정 기록 | POST /pages/{p}/state/decisions |
| `madang artifact add <path>` | 산출물 등록 | POST /pages/{p}/state/artifacts |
| `madang commit -m "…"` | 코드 저장소 커밋 (민감정보 검사 포함) | POST /spaces/{s}/repo/commit |
| `madang push` | 코드 저장소 푸시. 강제 푸시 불가, 브랜치는 현재 브랜치만 | POST /spaces/{s}/repo/push |
| `madang promote <block>` | 블록 파일을 코드 저장소 docs/로 복사·커밋 | POST /pages/{p}/blocks/{b}/promote |
| `madang view create --template T --data bNN` | 뷰 블록 생성 | POST /pages/{p}/blocks |
| `madang help [cmd]` | 사용법 | — |

모든 명령은 `MADANG_PAGE` 없이 실행되면 거부한다(에이전트 밖에서 사람이 쓸 땐 `--page` 명시).

## 7. core API (v1, 발췌)

전체는 `core/openapi.yaml`. 여기서는 Phase A에 필요한 것만.

```
GET    /health
GET    /spaces                              목록
POST   /spaces                              {slug, title, repo?}
PATCH  /spaces/{s}                          {title?, repo?}
DELETE /spaces/{s}                          (페이지가 있으면 409)
GET    /spaces/{s}/pages                    목록 + 미리보기(상태, 마지막 메시지, 블록 수)
POST   /spaces/{s}/pages                    {title, kind?}
GET    /pages/{p}                           page.md + 블록 목록(머리부만)
PATCH  /pages/{p}                           {title?, pinned?, tags?, blocks_order?}
DELETE /pages/{p}                           폴더 삭제 + 커밋
GET    /pages/{p}/blocks/{b}                파일 전체
PUT    /pages/{p}/blocks/{b}                파일 전체 교체 (앱에서 편집)
PATCH  /pages/{p}/blocks/{b}                머리부만 (bindings, active_preset 등)
DELETE /pages/{p}/blocks/{b}
POST   /pages/{p}/blocks                    {type, name, content|template+bindings}
GET    /pages/{p}/memory                    root/space/state 세 파일
PUT    /pages/{p}/memory/{layer}            편집 (검사기 통과해야 저장)
POST   /pages/{p}/messages                  {text, target:{block?, elements?, mode?}} → run 시작
GET    /pages/{p}/runs/{n}
POST   /pages/{p}/runs/{n}/cancel
POST   /pages/{p}/decisions/{id}/answer     ask_human 재개 {choice}
GET    /pages/{p}/preview-input             다음 호출 입력 구성과 토큰 추정 (target 파라미터)
GET    /pages/{p}/unknown-files
POST   /pages/{p}/unknown-files/{path}      {action: artifact|keep|delete}
GET    /trash                               최근 삭제 (git log 기반)
POST   /trash/{commit}/restore
GET    /templates                           내장 + 설치
GET    /templates/{name}/schema
WS     /events                              아래 이벤트 스트림
```

이벤트:
`space.*`, `page.created|updated|deleted`, `block.added|updated|deleted`, `run.started|assembled|progress|finished|failed`, `page.unknown_files`, `flow.waiting {decision}`, `memory.updated`.

## 8. 검사기

| 검사 | 시점 | 실패 시 |
|---|---|---|
| state.md 스키마·상한·경로 | run 후, 메모리 편집 저장 시 | run: repair 노드 1회 → 실패면 ask_human. 편집: 400과 오류 위치 |
| 미등록 파일 | run 후 (`git status --porcelain` 전후 비교, 코드 저장소와 페이지 폴더) | `page.unknown_files` 이벤트. 사용자 처리 전까지 페이지 상단 표시 |
| done 조건 | judge | verify 결과 없으면 review로 강등 |
| 민감정보 (Phase D) | commit 전 | 커밋 중단, 위치 표시 |
| 인계 테스트 (Phase D) | validate | 보강 요청 |

## 9. git 규칙 (앱 홈)

- 커밋 단위: run 하나, 또는 사용자의 편집 저장 하나, 또는 삭제 하나.
- 메시지: `[<page-id>] run <n> · <runner>/<model> · <changed files 요약>` / `[<page-id>] edit <block>` / `[<page-id>] delete <block|page>`.
- 삭제는 `git rm`. "최근 삭제"는 `git log --diff-filter=D`로 만든다. 복구는 `git checkout <commit>^ -- <path>` 후 커밋.
- 완전 삭제(Phase D): `git filter-repo`. 별도 확인.
- 원격 푸시: 설정 시 run 커밋 후 자동 (`config.madang.yaml: home_remote`).

## 10. 템플릿 규격

```
templates/<name>/
├ template.yaml     name, version, title, slots, editable
├ page.html         data-bind 표시가 있는 HTML. 외부 네트워크 없음
├ schema.json       슬롯별 JSON Schema
├ sample.json       슬롯별 샘플
├ theme.json        스타일 변수 기본값
└ preview.png
```

```yaml
# template.yaml
name: resume
version: 1
title: 이력서
slots:
  base:    {schema: "#/base",    required: true,  label: 기본 데이터}
  overlay: {schema: "#/overlay", required: false, label: 덮어쓰기}
editable:
  text: true        # 편집 모드에서 텍스트 직접 수정 허용
  style: [color.accent, font.size]
```

`page.html` 규칙:
- `data-bind="slot.path"`: 텍스트 바인딩. `data-each="slot.path"`: 반복. `data-attr-src="…"`: 속성.
- 덮어쓰기: 여러 슬롯이 같은 경로를 가지면 뒤 슬롯이 이긴다(overlay 패턴).
- `madang.js`(런타임)가 렌더링, 요소 → 데이터 경로 역추적, 선택 하이라이트, 앱 브리지를 담당한다. 템플릿은 스크립트를 넣지 않는다(Phase F까지).

## 11. 결정기 인터페이스

```python
class Decider(Protocol):
    def decide(self, question: Question) -> Decision: ...

@dataclass
class Question:
    kind: Literal["choice", "yesno", "score"]
    prompt: str
    options: list[str] | None
    state: str                     # 관련 상태 텍스트 (짧게)

@dataclass
class Decision:
    choice: str | bool | int
    confidence: float
    by: str                        # rules | light_model | jev
```

체인: 앞 구현체의 confidence가 `min_confidence` 미만이면 다음으로. 마지막까지 미만이면 `ask_human`.

결정 지점(Phase A는 1번만, Phase D에서 전부):
1. 요청 종류 (choice)
2. 도구·모델 (choice, 라우팅 표가 답이므로 규칙만)
3. 막힘 판정 (yesno)
4. 인계 충분성 (score 1~5)
5. 새 파일 분류 (choice: artifact | scratch | keep)
6. 리뷰 통과 (yesno)

## 12. 설정 (config/madang.yaml)

```yaml
home_remote: git@github.com:woonyong-choi/madang-home.git   # 선택
core:
  port: 7470
  bind: 127.0.0.1
agents:
  claude_settings: ~/.claude/settings.json
  codex_config: ~/.codex/config.toml
limits:
  state_tokens: 2000
  block_input_tokens: 4000
  run_timeout_minutes: {design: 30, build: 20, small: 5, review: 10, explore: 5}
ui:
  language: ko
```

## 13. 보안 원칙

- core는 127.0.0.1에만 바인딩. 원격(Phase C)은 토큰 인증 + LAN.
- 템플릿 WebView는 `file://` 페이지 폴더만 접근, 네트워크 차단 (CSP). Phase F 커뮤니티 템플릿은 별도 origin 격리.
- secrets.yaml은 git 제외, 값은 API 응답에 절대 포함하지 않는다. API 데이터 블록은 `auth: secrets.<key>` 참조만.
- 에이전트 권한: `madang *` 허용, 날것의 push·force·rm -rf 거부를 설치 시 권고.
