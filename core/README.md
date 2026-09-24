# madang-core

Python 3.12 패키지 `madang`. 흐름 엔진, 실행기(claude/codex CLI 어댑터), 검사기, 앱 홈 저장(git), `madang` CLI를 담는다.

## 개발

[uv](https://docs.astral.sh/uv/)가 필요하다.

```
cd core
uv sync
uv run pytest -q
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

## 구조

```
madang/
├ cli.py        madang 명령 (typer)
├ config.py     앱 홈 경로, config/*.yaml 로딩
├ defaults/     앱 홈 기본 파일
├ store/        앱 홈 읽기·쓰기, git CLI 래퍼
├ api/  graph/  runners/  deciders/  validate/  procs/
```
