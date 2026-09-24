# madang-app

Madang 데스크톱 앱. Kotlin Multiplatform + Compose Multiplatform.

지금 타깃은 desktop(JVM: macOS, Windows)이다. Android·iOS는 이후에 추가한다.

## 요구 사항

- JDK 21
- Gradle은 설치하지 않아도 된다. 저장소의 wrapper(`./gradlew`)를 쓴다.

## 모듈

```
app/
├ shared/    공용 코드 (commonMain): core API 클라이언트, 앱 루트 Composable
└ desktop/   JVM 데스크톱 진입점 (창, 패키징)
```

- `CoreClient`: madang-core HTTP 클라이언트(Ktor). 기본 주소 `http://127.0.0.1:7470`.
- `MadangApp()`: 앱 루트 Composable. 3열(탐색 / 목록 / 본문) 자리표시.

## 명령

모든 명령은 `app/`에서 실행한다. Windows에서는 `gradlew.bat`을 쓴다.

```sh
./gradlew :shared:test          # 공용 모듈 테스트
./gradlew :desktop:run          # 앱 실행
./gradlew :desktop:compileKotlin
```

자동 확인용 실행: `MADANG_SMOKE=1`이면 첫 화면을 그린 뒤 3초 후 스스로 종료한다(exit 0).

```sh
MADANG_SMOKE=1 ./gradlew :desktop:run
```

## core API 클라이언트 생성

`../core/openapi.yaml`이 있으면 빌드 전에 `:shared:openApiGenerate`가 Kotlin 모델·클라이언트를
`shared/build/generated/openapi/`에 만들고 `commonMain`에 포함한다(패키지 `madang.api`,
Ktor + kotlinx-serialization). 파일이 없으면 이 작업은 건너뛴다.

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
