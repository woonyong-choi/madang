# madang-app

Madang 데스크톱 앱. Kotlin Multiplatform + Compose Multiplatform.

지금 타깃은 desktop(JVM: macOS, Windows)이다. Android·iOS는 이후에 추가한다.

## 요구 사항

- JDK 21
- Gradle은 설치하지 않아도 된다. 저장소의 wrapper(`./gradlew`)를 쓴다.

## 모듈

```
app/
├ shared/    공용 코드 (commonMain): core 연결, 이벤트 스트림, ViewModel, 화면
└ desktop/   JVM 데스크톱 진입점: 창, core 프로세스 기동, 앱 설정 파일, 가짜 core
```

- `CoreClient`: core 연결 하나. 생성된 API 클라이언트(`madang.api.client`)가 HTTP 클라이언트를
  함께 쓴다. `core.api(::PagesApi)`처럼 필요한 클라이언트를 얻는다.
- `CoreLocator`: 설정의 core 주소 → `<앱 홈>/core.port` → `http://127.0.0.1:7470` 순서로
  `/health`를 확인하고, 없으면 core를 띄운 뒤 응답할 때까지 기다린다.
- `EventStream`: `WS /events`를 `Flow`로 바꾼다. 끊기면 다시 붙고, 붙을 때마다 전체 재조회 신호
  (`Resync`)를 보낸다.
- 화면: 시작 → (앱 홈이 없으면) 온보딩 → 메인 ↔ 설정. 화면마다 ViewModel + `StateFlow`.
- 메인 화면은 3열이다: 공간·태그 트리 / 페이지 카드 목록 / 페이지 본문(블록 흐름). 창이 좁으면
  (목록 또는 공간) + 본문 2열, 더 좁으면 한 열만 보인다.

## 메인 화면 조작

| 키·동작 | 결과 |
|---|---|
| 위·아래 | 공간 열: 공간·태그 고르기. 목록 열: 페이지 고르고 열기 |
| 오른쪽 · Enter | 다음 열로(공간 열에서 오른쪽은 접힌 공간을 먼저 펼친다) |
| 왼쪽 · Backspace | 이전 열로(공간 열에서 왼쪽은 펼친 공간을 접거나 상위로) |
| Cmd/Ctrl+1/2/3 | 공간 / 목록 / 본문 열 포커스 |
| Cmd/Ctrl+N | 고른 공간에 새 페이지 |
| 카드에 마우스 | 고정·태그·이동·삭제 빠른 동작 |
| 카드를 공간·태그로 끌기 | 그 공간으로 이동, 그 태그 추가 |
| 오른쪽 클릭 | 공간: 포커스·이름 변경·저장소 연결·삭제. 카드: 고정·태그·이동·삭제 |

목록은 고정된 페이지가 먼저이고, 공간별 정렬(갱신·생성·제목)을 따른다. 날짜순이면 오늘·어제·지난
7일·지난 30일·월별로 묶는다. 필터는 상태와 태그로 건다. 본문의 router 메시지와 run 카드, 지난 대화의
메시지는 한 줄로 접히며 클릭하거나 "모두 펼치기"로 펼친다. doc 블록은 Compose 마크다운으로 그리고,
mermaid는 코드 블록으로 보인다.

앱은 앱 홈 파일을 읽거나 쓰지 않는다(`core.port` 읽기만 예외). 앱이 쓰는 파일은 앱 설정
`settings.json` 하나다(macOS `~/Library/Application Support/Madang`, Windows `%APPDATA%\Madang`,
그 밖 `~/.config/madang`, `MADANG_APP_CONFIG_DIR`로 변경).

## 명령

모든 명령은 `app/`에서 실행한다. Windows에서는 `gradlew.bat`을 쓴다.

```sh
./gradlew :shared:test          # 공용 모듈 테스트
./gradlew :desktop:test         # 데스크톱 모듈 테스트
./gradlew :desktop:run          # 앱 실행
./gradlew :desktop:compileKotlin
./gradlew ktlintCheck           # 코드 스타일 검사
./gradlew ktlintFormat          # 코드 스타일 자동 수정
```

코드 스타일은 Android Kotlin 스타일 가이드(ktlint `android_studio`)를 따른다. 규칙은 `.editorconfig`에 있다.

자동 확인용 실행: `MADANG_SMOKE=1`이면 첫 화면을 그린 뒤 3초 후 스스로 종료한다(exit 0).

```sh
MADANG_SMOKE=1 ./gradlew :desktop:run
```

## core 연결

`./gradlew :desktop:run`은 떠 있는 core가 없으면 `uv run --project ../core madang serve`로
core를 띄운다. 설정 화면의 "core 실행 파일"을 지정하면 `<파일> serve`를 쓴다. 실패하면 시작
화면에 원인과 "다시 시도"가 보인다.

core 없이 화면을 개발하려면 가짜 core를 쓴다. `../core/openapi.yaml`의 응답 예시로 답하고,
연결되면 계약의 이벤트 예시를 차례로 보낸다. 앱 설정 파일은 쓰지 않는다.

```sh
MADANG_FAKE_CORE=1 ./gradlew :desktop:run                      # 앱 홈 없음 → 온보딩
MADANG_FAKE_CORE=1 MADANG_FAKE_HOME=1 ./gradlew :desktop:run   # 메인 화면부터
```

페이지가 있는 화면을 보려면 픽스처 앱 홈을 쓴다. `desktop/src/test/resources/fixture-home/`의
공간·페이지·블록 파일로 답하고, 고정·이동·삭제 같은 요청은 메모리에만 반영하며 이벤트를 보낸다.

```sh
MADANG_FAKE_CORE=1 MADANG_FAKE_FIXTURE=src/test/resources/fixture-home ./gradlew :desktop:run
```

`./gradlew :desktop:test`는 이 픽스처로 메인 화면을 화면 밖에서 그려
`desktop/build/screenshots/`에 `wide.png`(3열), `narrow.png`(2열), `page.png`(1열)를 남긴다.

앱 홈 상태(`GET/POST /home`)와 라우팅 표(`GET/PUT /config/routes`)는 아직 계약 파일에 없다.
`CoreSetupApi`가 이 경로를 쓰며, core가 `/home`을 모르면 앱 홈이 있다고 보고 메인으로 간다.

## core API 클라이언트 생성

컴파일 전에 `:shared:openApiGenerate`가 `../core/openapi.yaml`에서 Kotlin 모델·클라이언트를
`shared/build/generated/openapi/`에 만들고 `commonMain`에 포함한다(패키지 `madang.api`,
Ktor + kotlinx-serialization). 계약은 이 파일 하나이며 앱에 손으로 쓴 API 모델은 없다.

이벤트(`Event`)는 생성기가 oneOf를 제대로 만들지 못하므로 `EventEnvelope`로 `type`을 먼저 읽고
구체 이벤트(`RunProgressEvent` 등)로 다시 해석한다. 생성된 `EventsApi`는 쓰지 않는다.

다른 명세 파일로 생성하려면:

```sh
./gradlew :shared:openApiGenerate -Pmadang.openapiSpec=/path/to/openapi.yaml
```

## 패키징

`compose.desktop.application`에 `Dmg`(macOS), `Msi`(Windows)가 설정되어 있다.

```sh
./gradlew :desktop:packageDmg    # macOS
./gradlew :desktop:packageMsi    # Windows
```
