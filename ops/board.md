# Madang 빌드 보드

오너가 유지한다. 상태: todo | running | review | fixing | blocked | done. 시도는 같은 단계의 실행 횟수.

| WP | 제목 | 역할 | 의존 | 상태 | 담당(tool/model) | 시도 | 시작 | 가정·비고 |
|---|---|---|---|---|---|---|---|---|
| WP-01 | core 뼈대 | builder-core | - | todo | | 0 | | |
| WP-02 | state 스키마·검사기 | builder-core | 01 | todo | | 0 | | |
| WP-03 | 실행기 (claude/codex) | builder-core | 01 | todo | | 0 | | |
| WP-04 | madang CLI (에이전트용) | builder-core | 02 | todo | | 0 | | |
| WP-05 | 입력 조립 + 단발 실행 | builder-core | 03,04 | todo | | 0 | | |
| WP-06 | LangGraph 흐름 | builder-core | 05 | todo | | 0 | | |
| WP-07 | API + 이벤트 | builder-core | 06 | todo | | 0 | | |
| WP-08 | CLI를 API 경유로 | fixer | 07 | todo | | 0 | | |
| WP-09 | KMP 뼈대 | builder-app | - | todo | | 0 | | |
| WP-10 | core 연결·온보딩·설정 | builder-app | 09,07 | todo | | 0 | | |
| WP-11 | 레이어 0 3열 (Notebook Navigator 100%) | builder-app | 10 | todo | | 0 | | |
| WP-12 | 입력창·메모리·띠·결정 카드 | builder-app | 11 | todo | | 0 | | |
| WP-13 | 템플릿 런타임 + 내장 4개 | builder-web | - | todo | | 0 | | |
| WP-14 | 뷰 블록·레이어 1 | builder-app | 12,13 | todo | | 0 | | |
| WP-15 | 보기/편집·레이어 2 | builder-app | 14 | todo | | 0 | | |
| WP-16 | 패키징 (dmg/msi + core 바이너리) | builder-app | 15,08 | todo | | 0 | | |
| WP-17 | 권한 마법사·문서 | fixer | 16 | todo | | 0 | | |
| WP-18 | 수용 점검 | reviewer | 17 | todo | | 0 | | |

리뷰 과업(`WP-xx-R`)은 완료 시 오너가 아래에 추가한다.

## 결정 필요 (사람)
(없음)

## 완료
(없음)
