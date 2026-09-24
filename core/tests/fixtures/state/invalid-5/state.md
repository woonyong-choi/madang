---
status: review
kind: design
tier: 1
attempts: 0
decisions:
  - id: D1
    topic: 갱신 경합 해결
    choice: refresh-lock
    options: [refresh-lock, client-retry]
    state: confirmed
  - id: D1
    topic: 세션 저장소
    choice: redis
    options: [memory, sqlite]
    state: approved
---
## 목표
결정 기록이 잘못된 상태 파일.

## 다음 할 일
결정을 정리한다.
