# Madang (마당)

AI 코딩 에이전트와 함께 일하는 사람을 위한, 문서·화면·실행이 한 페이지에 있는 작업 공간.

- Claude Code와 Codex를 가리지 않는 중립 작업대. 다음 일을 누구에게 줄지는 규칙이 정한다.
- 보이는 메모리. 에이전트가 매 호출 읽는 것이 파일로 있고, 사람이 고친다. 세션은 버리고 파일만 잇는다.
- 살아 있는 문서. 화면은 데이터에 연결되어 있고, 표현은 템플릿이, 내용은 데이터가, 판단은 AI가 맡는다.
- 배포되는 문서. 페이지 하나를 내 도메인으로 낸다.

## 상태

설계 단계. 아직 실행 가능한 코드가 없다.

## 구조

```
docs/        승인된 문서
docs/ai/     AI가 쓴 초안. 승인되면 docs/로 이동
core/        Python: 흐름 엔진(LangGraph), 실행기, 저장, madang CLI
app/         Kotlin Multiplatform: macOS · Windows (· Android · iOS)
templates/   내장 템플릿
ops/         빌드 오케스트레이션 (오너·빌더 프롬프트, 보드, 보고)
```

## 문서

읽는 순서: [비전](docs/ai/00-vision.md) → [아키텍처](docs/ai/01-architecture.md) → [core 스펙](docs/ai/02-core-spec.md) → [앱 스펙](docs/ai/03-app-spec.md) → [로드맵](docs/ai/04-roadmap.md) → [결정 기록](docs/ai/05-decisions.md) → [빌드 오케스트레이션](docs/ai/06-build-orchestration.md)

## 라이선스

MIT
