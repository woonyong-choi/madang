# 제3자 고지

이 저장소에는 아래 오픈 소스 프로젝트에서 옮긴 코드가 들어 있다. 옮긴 파일의
머리 주석에 원본 경로를 적었다.

## Orca

- 출처: https://github.com/stablyai/orca (커밋 25d7c21fcb793e0e8b44d9f62e75068182ec0f62)
- 라이선스: MIT
- 옮긴 곳: `core/madang/usage/` (Claude Code·Codex 사용 기록 파서, 사용량 창 길이와 경고 기준)

```
MIT License

Copyright (c) 2026 Lovecast Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 앱 배포물(dmg)에 함께 실리는 것

macOS 앱(`Madang.app`)에는 이 고지 파일이 `Contents/app/resources/THIRD_PARTY_NOTICES.md`로
들어 있고, 아래 구성 요소가 함께 실린다. 코드를 옮긴 것이 아니라 빌드 산출물을 그대로 싣는다.

| 구성 요소 | 위치(앱 안) | 라이선스 |
|---|---|---|
| Java 런타임(OpenJDK, jlink) | `Contents/runtime/` | GPL-2.0 + Classpath Exception (원문: 런타임의 `legal/`) |
| Kotlin·Compose Multiplatform·Ktor·kotlinx 라이브러리 | `Contents/app/*.jar` | Apache-2.0 |
| KCEF·JCEF(Chromium Embedded) | `Contents/app/kcef-*.jar`, `jcef-*.jar` | Apache-2.0(KCEF), BSD-3-Clause(JCEF·CEF) |
| 문서 렌더러의 marked | `Contents/app/desktop-*.jar`의 `madang-runtime/` | MIT (`templates/_runtime/THIRD_PARTY_NOTICES.md`) |
| core(PyInstaller onedir) | `Contents/app/resources/madang-core/` | 아래 참조 |

- core 번들에는 Python 인터프리터(PSF-2.0)와 core의 실행 의존성(FastAPI, uvicorn, LangGraph,
  tiktoken, pydantic 등)이 들어 있다. 패키지마다 라이선스 원문은 번들 안
  `madang-core/_internal/<패키지>-<버전>.dist-info/`에 그대로 있다.
- PyInstaller 부트로더는 GPL-2.0에 부트로더 예외(번들 배포 허용)가 붙은 라이선스다.
- Chromium 엔진 번들은 dmg에 넣지 않는다. 브라우저·문서 탭을 처음 열 때 KCEF가 내려받아 앱
  설정 폴더(`kcef-bundle/`)에 둔다. 그 번들의 고지는 번들 안의 라이선스 파일을 따른다.
