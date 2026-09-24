# madang-core

Python 3.12 패키지 `madang`. 흐름 엔진, 실행기(claude/codex CLI 어댑터), 검사기, 프로젝트 기록 저장(`<project>/.madang/`), `madang` CLI를 담는다.

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

`madang init`은 앱 홈(전역 설정 폴더)을 만든다. 경로는 `--home` > `MADANG_HOME` > `~/.madang` 순서로 정한다. 앱 홈은 git 저장소가 아니며 페이지를 담지 않는다.

```
<home>/
├ config/
│  ├ madang.yaml     전역 설정과 프로젝트 목록(projects)
│  ├ routes.yaml     라우팅 표
│  └ runners.yaml    도구·모델 목록과 실행 방법
├ root.md            모든 실행이 읽는 공통 메모(메모리 1층)
├ templates/         사용자 설치 템플릿(있으면)
├ core.db            흐름 체크포인트(core가 만든다)
└ core.port          실행 중인 core의 포트
```

이미 초기화된 홈에서 다시 실행하면 기존 파일을 덮어쓰지 않고 빠진 파일만 만든다. 페이지를 앱 홈 안(`spaces/`)에 두던 예전 구조를 만나면 옮기는 방법과 함께 거부한다.

### 프로젝트와 페이지 만들기

```
uv run madang project add <폴더> [--id 아이디] [--title "제목"] [--home PATH]
uv run madang project list [--home PATH]
uv run madang page new --project <아이디> --title "제목" [--kind build] [--slug 슬러그] [--home PATH]
```

프로젝트는 로컬 폴더(보통 git 저장소)다. `project add`는 폴더에 기록 폴더 `.madang/`을 만들고 `config/madang.yaml`의 `projects`에 등록한 뒤 아이디를 출력한다. 아이디를 생략하면 폴더 이름을 쓰고, 겹치면 `-2`처럼 번호를 붙인다. 이미 있는 `.madang/` 파일은 덮어쓰지 않는다.

```
<project>/
└ .madang/
   ├ .gitignore      기본 "*": 기록을 커밋하지 않는다
   ├ project.md      프로젝트 메모(메모리 2층)
   ├ pages/<page-id>/
   │  ├ page.md      머리부: 제목, 상태, blocks 순서
   │  ├ state.md     메모리 3층
   │  ├ log.md       대화 로그
   │  ├ blocks/  runs/  scratch/
   └ trash/          지운 페이지·블록(복원하면 제자리로 옮긴다)
```

기록을 커밋할지는 사용자가 정한다. `config/madang.yaml`에서 `commit_records: true`로 두면 새 프로젝트의 `.gitignore`는 `pages/*/scratch/`와 `trash/`만 뺀다. core는 어떤 기록도 스스로 커밋하지 않는다.

`page new`는 프로젝트의 `.madang/pages/<YYYY-MM-DD-슬러그>/`에 page.md, state.md, log.md를 만들고 페이지 id를 출력한다. `--kind`를 생략하면 routes.yaml의 기본 종류를 쓰고, 슬러그를 생략하면 제목에서 만든다.

### 페이지 실행

```
uv run madang run <page-id> "<요청>" --tool claude|codex --model <모델> [--effort medium] [--target b05] [--home PATH]
```

페이지의 한 단계를 새 세션에서 실행한다. 프롬프트를 조립해 실행기(claude/codex CLI)에 넘기고, 끝나면 state.md를 검사한 뒤 결과를 `runs/N.json`에 기록한다. `--target`은 요청이 가리키는 블록 id이다. 작업 폴더는 페이지가 속한 프로젝트 폴더다. 실행이 만들었지만 등록하지 않은 파일은 전후 비교로 찾는다(프로젝트가 git 저장소면 `git status`, 아니면 파일 목록).

### 페이지 검사

```
uv run madang validate <페이지 폴더 | state.md> [--repo PATH] [--json]
```

state.md(와 page.md)를 검사한다. 문제가 있으면 위치와 함께 출력하고 exit 1로 끝난다. `repo:` 산출물은 `--repo` 또는 페이지가 속한 프로젝트 폴더를 기준으로 확인한다.

### core API 서버

```
uv run madang serve [--port 7470] [--home PATH]
uv run madang openapi
```

`serve`는 core API를 127.0.0.1에만 묶어 띄운다. 포트가 쓰이고 있으면 다음 포트를 쓰며, 고른 포트는 `<home>/core.port`에 적고 종료할 때 지운다. 페이지 기록과 앱 홈 설정에 쓰는 프로세스는 core 하나뿐이며, 앱과 에이전트 명령이 모두 이 API로 요청한다. `openapi`는 API 계약(OpenAPI YAML)을 출력한다. 서버의 `/openapi.json`이 주는 문서와 같다.

### 에이전트 명령

에이전트가 실행 중에 부작용을 요청하는 명령이다. 명령은 파일을 직접 고치지 않고 core API로 요청을 보내므로 `madang serve`가 떠 있어야 한다. core 주소는 `MADANG_CORE_URL` > `<home>/core.port` > `http://127.0.0.1:7470` 순서로 정한다. core에 연결할 수 없으면 오류를 내고 exit 2로 끝난다. 대상 페이지는 `MADANG_PAGE`(페이지 id)로 정하며, 에이전트 밖에서 사람이 쓸 때는 `--page <id>`를 준다. 둘 다 없으면 거부한다. 앱 홈은 `--home` 또는 `MADANG_HOME`.

```
uv run madang help [command]
uv run madang task T2 --status doing [--title "갱신 잠금"] [--due 2026-09-26]
uv run madang decide D2 --topic "갱신 경합" --choice refresh-lock --options refresh-lock,client-retry [--supersedes D1]
uv run madang artifact add blocks/b05-race.md      # 또는 프로젝트 폴더 안의 파일, repo:<path>
uv run madang commit -m "feat: add refresh lock"
uv run madang push
uv run madang view create --template resume --data b03 [--data overlay=b04]
```

- state.md와 page.md를 고친 뒤에는 core가 검사기를 돌리고, 실패하면 변경을 되돌린 뒤 오류와 함께 exit 1로 끝난다. 본문은 그대로 두고 머리부만 고친다.
- `commit`, `push`는 페이지가 속한 프로젝트 폴더가 git 저장소일 때만 동작하며, 아니면 거부한다. `commit`은 비밀 파일로 보이는 이름(`.env`, `*.pem`, `id_rsa*` 등)이 있으면 거부한다.
- `push`는 현재 브랜치를 같은 이름의 원격 브랜치로만 보내며 강제 푸시는 하지 않는다.
- `view create`는 새 블록 id를 받아 `blocks/bNN-<template>.view.md`를 만들고 page.md `blocks` 끝에 붙이며, 만든 파일을 산출물로 등록한다. 템플릿은 앱 홈 `templates/`, `MADANG_TEMPLATES`, 내장 템플릿(table, decisions, tasks, resume) 순서로 찾는다.
- 블록 id는 `bNN`으로 늘어나며 삭제된 id도 다시 쓰지 않는다(`blocks/.last`).
- `decide`와 `view create`는 `MADANG_PAGE`로 부를 때(에이전트 실행 안)만 진행 중인 실행 번호를 붙인다. 사람이 `--page`로 부르면 흐름이 돌고 있어도 붙이지 않는다. `decide`의 `by`는 `--by` > `MADANG_BY` > `agent`(`MADANG_PAGE` 사용 시) / `human` 순서로 정한다.

## 구조

```
madang/
├ cli.py        madang 명령 (typer)
├ cli_agent/    에이전트 명령 (core API 클라이언트)과 core가 쓰는 변경 로직
├ config.py     앱 홈 경로, config/*.yaml 로딩
├ defaults/     앱 홈과 .madang/ 기본 파일
├ store/        프로젝트·페이지 기록 읽기·쓰기, 휴지통, git CLI 래퍼
├ api/  graph/  runners/  deciders/  validate/  procs/
```
