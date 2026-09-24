---
status: doing
kind: build
tier: 1
attempts: 0
owner: codex/gpt-6-sol
decisions:
  - id: D1
    topic: 레이아웃
    choice: two-column
    options: [two-column, single-column]
    by: claude/opus-5-5
    run: 1
    state: confirmed
    supersedes: null
tasks:
  - {id: T1, title: 템플릿 초안, status: done}
  - {id: T2, title: 경력 데이터 연결, status: doing, due: 2026-09-26}
artifacts:
  - blocks/b05-layout.md
---
## 목표
경력 데이터에 연결된 이력서 화면을 만든다. 데이터를 고치면 화면이 바뀌면 완료.

## 결정 사항
D1: 2단 레이아웃.

## 현재 상태
템플릿 초안은 blocks/b05-layout.md에 있다.

## 다음 할 일
1. 경력 데이터 블록을 만든다.
2. 뷰 블록에 연결한다.

## 막힌 점

## 로그
2026-09-24 | codex/gpt-6-sol | run 1 | 템플릿 초안
