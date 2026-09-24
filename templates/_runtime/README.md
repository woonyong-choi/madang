# _runtime

WebView와 게시가 함께 쓰는 런타임.

| 파일 | 역할 |
|---|---|
| `document.js` | 문서 렌더러. 마크다운(머리부·표·코드)과 view 펜스를 HTML로 그린다 |
| `document.css` | 렌더 결과의 기본 모양. 앱 토큰(`--app-*`)을 따른다 |
| `madang.js` | 템플릿 런타임(바인딩, 선택, 편집, 브리지). `renderMarkdown`·`renderDocument`는 `document.js`를 쓴다 |
| `vendor/marked.umd.js` | 마크다운 해석기(MIT). 고지는 `THIRD_PARTY_NOTICES.md` |

## 문서 렌더러 `document.js`

렌더러는 하나다. 앱 문서 탭과 게시가 같은 함수를 부르므로 로컬과 웹의 결과가 같다.
DOM 없이 문자열만 다루므로 브라우저와 Node 양쪽에서 돈다. 네트워크에 접근하지 않는다.

```html
<link rel="stylesheet" href="_runtime/document.css">
<script src="_runtime/vendor/marked.umd.js"></script>
<script src="_runtime/document.js"></script>   <!-- window.madangDocument -->
```

```js
const {renderDocument, listViews} = require('./_runtime/document.js'); // Node
```

| 함수 | 설명 |
|---|---|
| `renderDocument(markdown, context)` | `{html, frontMatter, views}`. `html`은 `<div class="madang-document">` 하나 |
| `listViews(markdown)` | 문서의 view 펜스 `[{key, name, pin, data}]`. 호스트가 이것으로 `context.views`를 채운다 |
| `mountDocument(target, markdown, context)` | 브라우저 전용. 결과를 요소에 넣고 뷰어 iframe 높이를 맞춘다 |

렌더 규칙

- 맨 앞 `---` 머리부는 떼어 `frontMatter`로 돌려주고, 접힌 `<details class="madang-frontmatter">`로 보여 준다.
- 표·코드 블록은 GFM 그대로. 원문 HTML은 글자로 보여 준다(실행하지 않는다).
- 링크는 `http`·`https`·`mailto`·상대 경로만 남긴다. 이미지는 상대 경로와 `data:image`만 불러오고 원격 이미지는 링크로 바꾼다.

### view 펜스

````md
```view resume/basic data=./base.json
```
````

정보 문자열은 `view <이름>[@해시] data=<경로>`다. `key`는 `view`를 뺀 나머지(공백 하나로 정리)이고,
`context.views[key]`가 그 펜스를 어떻게 그릴지 정한다. core `madang.viewers.document_context()`가 같은 규칙으로
이 값을 만든다.

```js
context = {
  views: {
    'resume/basic data=./base.json': {
      status: 'ok',            // ok | invalid | broken | missing
      html: '<!doctype html>…', // ok일 때 뷰어 진입 HTML
      data: {…},                // 데이터(JSON 값)
      errors: [{path: 'work[0].company', message: 'is required'}], // invalid일 때
      message: '…',             // ok가 아닐 때 이유
    },
  },
  tokens: {bg, text, accent, font, radius}, // 앱 토큰
};
```

- `ok`: `sandbox="allow-scripts"`만 있는 iframe(`srcdoc`)에 뷰어를 넣는다. 부모 문서에 접근할 수 없다.
- `invalid`·`broken`·`missing`(항목 없음 포함): iframe을 만들지 않고, 이유와 어긋난 경로 목록, 데이터 표를 보여 준다.

iframe 문서에는 렌더러가 다음을 넣는다.

1. CSP `default-src 'none'`(인라인 스크립트·스타일과 `data:` 이미지·글꼴만 허용). 뷰어는 외부 자원을 불러오지 못한다.
2. `<script type="application/json" id="madang-view-data">` 데이터.
3. 문서 높이를 부모에 알리는 작은 스크립트(`mountDocument`가 받아 iframe 높이를 맞춘다).
4. 맨 끝에 앱 토큰 `--app-bg`, `--app-text`, `--app-accent`, `--app-font`, `--app-radius`를 `!important`로 둔다.
   주지 않았거나 `;{}<>\`가 든 값은 `initial`이 된다. 뷰어는 토큰을 읽기만 하고(`var(--app-accent, 기본값)`),
   정의하거나 덮어쓰지 못한다.

`srcdoc` 문서는 호스트 페이지의 CSP를 물려받는다. 뷰어 스크립트가 돌려면 호스트 CSP의 `script-src`에
`'unsafe-inline'`이 있어야 한다(`_tests/fixtures/document.html` 참고).

## 뷰어 규격

뷰어는 폴더 하나다(예: `../viewers/resume-basic/`).

```
<뷰어>/
├ viewer.json   {"name": "프로젝트/뷰어", "version": "1.0.0", "schema": "schema.json", "entry": "index.html"}
├ schema.json   데이터 JSON Schema
└ index.html    진입 HTML. 스타일·스크립트를 안에 담는다(외부 자원은 CSP로 막힌다)
```

- 이름은 `프로젝트/뷰어`(소문자·숫자·`.`·`_`·`-`). 같은 이름 등록은 오류다.
- 데이터는 `document.getElementById('madang-view-data').textContent`를 JSON으로 읽는다.
- 등록은 `~/.madang/viewers.yaml`의 참조(`name`, `source`, `follow: live|pinned`, `pinned`)이며 core `madang.viewers`가 읽고 쓴다.
  pinned 사본만 `~/.madang/cache/<해시>/<이름>/`에 둔다.

## 테스트

```
cd templates/_tests
npm install
npx eslint . ../_runtime
npx playwright test   # 템플릿 + 문서 렌더러(md, view iframe, 토큰, 표 대체, 외부 요청 0건)
```
