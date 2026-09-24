# madang-core

Python 3.12 패키지 `madang`. 흐름 엔진, 실행기(claude/codex CLI 어댑터), 검사기, 앱 홈 저장(git), `madang` CLI를 담는다.

## 개발

[uv](https://docs.astral.sh/uv/)가 필요하다.

```
cd core
uv sync
uv run pytest -q
```

코드는 Google Python Style Guide를 따르며 ruff로 검사한다(80열, Google 형식 docstring, import 정렬).

```
uv run ruff check .
uv run ruff format --check .
```

## 사용

```
uv run madang --version
uv run madang init [--home PATH]
```

`madang init`은 앱 홈을 만든다. 경로는 `--home` > `MADANG_HOME` > `~/.madang` 순서로 정한다.

```
<home>/
├ config/
│  ├ madang.yaml     전역 설정
│  ├ routes.yaml     라우팅 표
│  └ runners.yaml    도구·모델 목록과 실행 방법
├ root.md            모든 실행이 읽는 공통 메모
├ spaces/root/
│  ├ space.md        루트 공간
│  └ pages/
├ templates/         사용자 설치 템플릿
└ .gitignore         scratch/, secrets.yaml, core.db, core.port
```

앱 홈은 git 저장소이며 첫 커밋은 `[home] init`이다. 이미 초기화된 홈에서 다시 실행하면 기존 파일을 덮어쓰지 않고 성공으로 끝난다.

### 공간과 페이지 만들기

```
uv run madang space new <slug> [--title "제목"] [--repo PATH] [--home PATH]
uv run madang page new --title "제목" [--space root] [--kind build] [--slug 슬러그] [--home PATH]
```

`space new`는 `spaces/<slug>/`에 space.md와 빈 `pages/`를 만들고 슬러그를 출력한다. `--repo`는 공간의 코드 저장소 경로이며, 슬러그가 올바르지 않거나 이미 있으면 거부한다. `page new`는 `spaces/<space>/pages/<YYYY-MM-DD-슬러그>/`에 page.md, state.md, log.md를 만들고 페이지 id를 출력한다. `--kind`를 생략하면 routes.yaml의 기본 종류를 쓰고, 슬러그를 생략하면 제목에서 만든다.

### 페이지 실행

```
uv run madang run <page-id> "<요청>" --tool claude|codex --model <모델> [--effort medium] [--target b05] [--home PATH]
```

페이지의 한 단계를 새 세션에서 실행한다. 프롬프트를 조립해 실행기(claude/codex CLI)에 넘기고, 끝나면 state.md를 검사한 뒤 결과를 `runs/N.json`에 기록하고 앱 홈에 커밋한다. `--target`은 요청이 가리키는 블록 id이다. 작업 폴더는 공간의 코드 저장소이며, 없으면 페이지 폴더이다.

### 페이지 검사

```
uv run madang validate <페이지 폴더 | state.md> [--repo PATH] [--json]
```

state.md(와 page.md)를 검사한다. 문제가 있으면 위치와 함께 출력하고 exit 1로 끝난다. `repo:` 산출물은 `--repo` 또는 space.md의 `repo`를 기준으로 확인한다.

### core API 서버

```
uv run madang serve [--port 7470] [--home PATH]
uv run madang openapi
```

`serve`는 core API를 127.0.0.1에만 묶어 띄운다. 포트가 쓰이고 있으면 다음 포트를 쓰며, 고른 포트는 `<home>/core.port`에 적고 종료할 때 지운다. 앱 홈에 쓰는 프로세스는 core 하나뿐이며, 앱과 에이전트 명령이 모두 이 API로 요청한다. `openapi`는 API 계약(OpenAPI YAML)을 출력한다. 서버의 `/openapi.json`이 주는 문서와 같다.

### 에이전트 명령

에이전트가 실행 중에 부작용을 요청하는 명령이다. 명령은 파일을 직접 고치지 않고 core API로 요청을 보내므로 `madang serve`가 떠 있어야 한다. core 주소는 `MADANG_CORE_URL` > `<home>/core.port` > `http://127.0.0.1:7470` 순서로 정한다. core에 연결할 수 없으면 오류를 내고 exit 2로 끝난다. 대상 페이지는 `MADANG_PAGE`(페이지 id)로 정하며, 에이전트 밖에서 사람이 쓸 때는 `--page <id>`를 준다. 둘 다 없으면 거부한다. 앱 홈은 `--home` 또는 `MADANG_HOME`.

```
uv run madang help [command]
uv run madang task T2 --status doing [--title "갱신 잠금"] [--due 2026-09-26]
uv run madang decide D2 --topic "갱신 경합" --choice refresh-lock --options refresh-lock,client-retry [--supersedes D1]
uv run madang artifact add blocks/b05-race.md      # 또는 코드 저장소 안의 파일, repo:<path>
uv run madang commit -m "feat: add refresh lock"
uv run madang push
uv run madang promote b05
uv run madang view create --template resume --data b03 [--data overlay=b04]
```

- state.md와 page.md를 고친 뒤에는 core가 검사기를 돌리고, 실패하면 변경을 되돌린 뒤 오류와 함께 exit 1로 끝난다. 본문은 그대로 두고 머리부만 고친다.
- `commit`, `push`, `promote`는 공간의 코드 저장소(space.md의 `repo`)에서만 동작하며, 저장소가 없으면 거부한다. `commit`은 비밀 파일로 보이는 이름(`.env`, `*.pem`, `id_rsa*` 등)이 있으면 거부한다.
- `push`는 현재 브랜치를 같은 이름의 원격 브랜치로만 보내며 강제 푸시는 하지 않는다.
- `promote bNN`은 블록 파일을 코드 저장소 `docs/`로 복사(파일명에서 `bNN-` 접두 제거)하고, `repo:docs/<파일>`을 산출물로 등록한 뒤 그 파일만 커밋한다. `commit`처럼 비밀 파일로 보이는 이름이면 거부한다.
- `view create`는 새 블록 id를 받아 `blocks/bNN-<template>.view.md`를 만들고 page.md `blocks` 끝에 붙이며, 만든 파일을 산출물로 등록한다. 템플릿은 앱 홈 `templates/`, `MADANG_TEMPLATES`, 내장 템플릿(table, decisions, tasks, resume) 순서로 찾는다.
- 블록 id는 `bNN`으로 늘어나며 삭제된 id도 다시 쓰지 않는다(`blocks/.last`).
- state.md를 바꾸는 명령(`task`, `decide`, `artifact add`, `promote`)과 `view create`는 core가 앱 홈에 커밋한다. 그 페이지에서 흐름이 돌고 있으면 실행 커밋에 함께 들어간다. `decide`의 `by`는 `--by` > `MADANG_BY` > `agent`(`MADANG_PAGE` 사용 시) / `human` 순서로 정한다.

## 구조

```
madang/
├ cli.py        madang 명령 (typer)
├ cli_agent/    에이전트 명령 (core API 클라이언트)과 core가 쓰는 변경 로직
├ config.py     앱 홈 경로, config/*.yaml 로딩
├ defaults/     앱 홈 기본 파일
├ store/        앱 홈 읽기·쓰기, git CLI 래퍼
├ api/  graph/  runners/  deciders/  validate/  procs/
```
