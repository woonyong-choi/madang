# ops

Madang을 만드는 에이전트 오케스트레이션의 운영 파일. 설계는 `docs/ai/06-build-orchestration.md`.

| 파일 | 누가 쓰나 | 내용 |
|---|---|---|
| owner.md | 사람 | 오너 프롬프트. 기동 시 통째로 전달 |
| board.md | 오너 | 과업 현황 표 (진실) |
| log.md | 오너 | 한 줄 로그 |
| roles/*.md | 사람 | 역할별 프롬프트 템플릿. `{WP}`, `{SPEC}`, `{REPORT}`, `{BRANCH}`, `{EXTRA}` 치환 |
| tasks/WP-xx.md | 오너 | 과업 명세 |
| reports/WP-xx.md | 빌더·리뷰어 | 완료 보고 (고정 양식) |
| reports/WP-xx.done | 실행 명령 | 종료 표시 파일 (`git` 제외) |

기동:

```
cd ~/workspace/OSS/madang
tmux new -s agents-madang -n owner
claude --model claude-opus-5-5 --effort high "$(cat ops/owner.md)"
```
