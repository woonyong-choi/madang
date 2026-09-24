# templates

내장 템플릿과 WebView 런타임. 화면은 템플릿(HTML + 바인딩 표시)과 데이터(JSON)로만 만든다. 데이터를 쓰는 쪽은 HTML을 만들지 않는다.

| 이름 | 슬롯 | 내용 |
|---|---|---|
| `table` | `data` | `columns`(머리글)와 `rows`(행 배열의 배열)를 표로 |
| `decisions` | `state` | 상태 파일의 `decisions`를 state별(확정·제안·보류·대체됨) 카드로 |
| `tasks` | `state` | 상태 파일의 `tasks`를 status별(할 일·진행 중·막힘·완료) 열로 |
| `resume` | `base`(필수), `overlay`(선택) | 기본 정보·요약·경력·기술. overlay가 base를 덮는다 |

`index.json`은 위 목록을 기계가 읽는 형태(name, version, title, slots)로 둔다.

## 템플릿 폴더

```
<name>/
├ template.yaml   name, version, title, slots(순서가 덮어쓰기 순서), editable
├ page.html       바인딩 표시가 있는 HTML. 스크립트 없음, CSP로 외부 로드 차단
├ schema.json     슬롯별 JSON Schema (template.yaml의 "#/<키>"로 가리킴)
├ sample.json     슬롯별 샘플 데이터
├ theme.json      스타일 변수 기본값
└ preview.png     sample.json으로 그린 화면
```

## 바인딩 문법 (page.html)

| 속성 | 뜻 |
|---|---|
| `data-bind="slot.path"` | 요소 텍스트를 값으로 채운다 |
| `data-each="slot.path"` | 배열 항목마다 이 요소를 복제한다. 안쪽 경로는 `.`으로 시작하면 항목 기준(`.company`, 항목 자체는 `.`) |
| `data-where="key=a\|b"` | `data-each` 항목 거르기. `!=`는 제외. 경로의 인덱스는 원래 배열 기준으로 유지된다 |
| `data-attr-<name>="slot.path"` | 속성 값. 값이 없으면 속성을 지운다. `javascript:` 같은 URL은 쓰지 않는다 |
| `data-if` / `data-unless="slot.path"` | 값이 비었으면(또는 있으면) 요소를 지운다 |
| `data-madang-root` | 렌더 대상 요소. 없으면 `body` |

경로 표기: `work[1].company`. 첫 마디는 슬롯 이름이고, 값은 모든 슬롯을 template.yaml 순서로 합친 결과에서 읽는다.

덮어쓰기: 같은 경로면 뒤 슬롯이 이긴다. 객체는 깊게 합치고 배열은 통째로 바꾼다. 각 값이 어느 슬롯에서 왔는지 기억한다.

테마: `theme.json`의 `color.accent`는 CSS 변수 `--color-accent`, `font.size`는 `--font-size`가 된다. 숫자 크기에는 `px`를 붙인다.

## 런타임 `_runtime/madang.js`

의존성 없는 단일 파일(ES2020). 호스트(WebView)가 페이지에 주입한다. 페이지 CSP는 페이지 자체 스크립트를 막으므로 호스트 주입(문서 시작 시 스크립트 평가)으로 넣는다.

앱 → WebView (`window.madang`):

| 함수 | 설명 |
|---|---|
| `render(template, data, theme, mode)` | `template`: `{name, version, slots, html?}`(`slots`는 이름 배열, `{name}` 배열, 또는 순서 있는 객체). `data`: `{슬롯: JSON}`. `html`을 주면 그 마크업으로 교체, 아니면 현재 문서를 템플릿으로 쓴다. 성공 여부를 돌려준다 |
| `setMode('view' \| 'edit')` | 보기: 원래 동작, 링크는 `navigate`로 보고. 편집: 클릭 선택, Ctrl/Cmd+클릭 추가, Esc 해제, 십자 커서, 테두리 |
| `select(paths)` / `clearSelection()` | 경로로 하이라이트. 선택 정보(`selected`와 같은 모양)를 돌려준다 |
| `patchData(path, value, slot?)` | 값을 바꾸고 즉시 다시 그린다. 슬롯을 안 주면 그 값을 공급한 슬롯에 쓴다 |
| `renderMarkdown(source, {target?})` | md 렌더 진입점. `setMarkdownRenderer(fn)`로 렌더러를 붙이기 전에는 평문으로 보여 준다 |
| `sourceOf(path)`, `getData()`, `getMerged()`, `getSelection()`, `getMode()` | 조회 |

렌더된 요소에는 `data-madang-path`(데이터 경로)와 `data-madang-slot`(출처 슬롯)이 붙는다. 템플릿 고정 텍스트는 경로 `template:<위치>`, 출처 `template`이다.

WebView → 앱 메시지: `{source: "madang", type, payload}`

| type | payload |
|---|---|
| `ready` | `{version}` |
| `selected` | `{paths, slots, rects, htmlFragment}` |
| `hover` | `{path}` (편집 모드) |
| `navigate` | `{url}` (보기 모드 링크) |
| `error` | `{message}` |

전송: `window.madangBridge.post(json문자열)`이 있으면 그것을 쓴다(KCEF, Android `JavascriptInterface`, iOS 메시지 핸들러에 맞춰 붙인다). 없으면 `window.postMessage(msg)`와 `madang` CustomEvent(`detail`이 msg)로 보낸다. `madang.setBridge(adapter)`로 바꿔 끼울 수도 있다.

## 테스트와 미리보기

```
cd templates/_tests
npm install
npx playwright install chromium
npx playwright test     # 렌더, 덮어쓰기, 선택, patchData, 브리지, 외부 요청 0건
npm run preview         # <name>/preview.png 다시 만들기
```
