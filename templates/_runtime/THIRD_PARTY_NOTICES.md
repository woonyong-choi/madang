# 서드파티 고지

`_runtime/vendor/`에 들어 있는 외부 코드와 그 라이선스.

| 파일 | 출처 | 버전 | 라이선스 |
|---|---|---|---|
| `vendor/marked.umd.js` | [marked](https://github.com/markedjs/marked) `lib/marked.umd.js` | 18.0.14 | MIT (원문 `vendor/marked.LICENSE`) |

`vendor/marked.umd.js`는 npm 패키지의 파일을 고치지 않고 그대로 둔다. 버전을 올릴 때는
`_tests/package.json`의 `marked` 버전을 바꾸고 `npm install` 뒤 같은 파일을 다시 복사한다.
`_tests/document.spec.js`가 두 파일이 같은지 검사한다.
