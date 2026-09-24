/*
 * app.js - 앱 문서 탭의 호스트 스크립트.
 *
 * 앱이 render()로 넘긴 문서를 document.js로 그리고, 문서 안 링크를 누르거나
 * 블록을 더블클릭하면 `madang-app://` 주소로 탐색해 앱에 알린다. 앱은 그 탐색을 막고 요청대로
 * 탭을 연다. 직접 그리는 것은 없다(렌더러는 document.js 하나다).
 */
(function(root) {
  'use strict';

  const SCHEME = 'madang-app://';
  const TOKEN_NAMES = ['bg', 'text', 'accent', 'font', 'radius'];
  const SAFE_TOKEN = /^[^;{}<>\\]*$/;
  // 문서 안 이동(#제목)은 브라우저에 맡긴다.
  const IN_PAGE = /^#/;

  let blockCount = 0;

  // 문서 바탕도 뷰어 iframe과 같은 앱 토큰을 따른다.
  function applyTokens(tokens) {
    const style = root.document.documentElement.style;
    TOKEN_NAMES.forEach((name) => {
      const value = tokens && tokens[name];
      if (typeof value === 'string' && SAFE_TOKEN.test(value)) {
        style.setProperty('--app-' + name, value);
      } else {
        style.removeProperty('--app-' + name);
      }
    });
  }

  // 문서 옆 파일(상대 경로 이미지)이 문서 폴더에서 풀리게 한다.
  function applyBase(base) {
    const head = root.document.head;
    let element = head.querySelector('base');
    if (!base) {
      if (element) element.remove();
      return;
    }
    if (!element) {
      element = root.document.createElement('base');
      head.appendChild(element);
    }
    element.setAttribute('href', base);
  }

  /**
   * 문서를 그린다. 다시 부르면 스크롤 자리를 지키고, `follow`이며 블록이
   * 늘었으면 끝으로 간다. 처음 그릴 때는 문서처럼 맨 위부터 보인다.
   *
   * @param {{markdown: string, context: (!Object|undefined),
   *     base: (?string|undefined), follow: (boolean|undefined)}} payload
   *     `context`는 renderDocument()와 같고, `base`는 문서 폴더 URL이다.
   * @return {!Object} renderDocument()의 결과.
   */
  function render(payload) {
    const context = payload.context || {};
    applyTokens(context.tokens);
    applyBase(payload.base);
    const scroller = root.document.scrollingElement;
    const top = scroller.scrollTop;
    const target = root.document.getElementById('madang-page');
    const mount = root.madangDocument.mountDocument;
    const result = mount(target, payload.markdown, context);
    const count = target.querySelectorAll('.madang-block').length;
    const grew = blockCount > 0 && count > blockCount;
    scroller.scrollTop = payload.follow && grew ? scroller.scrollHeight : top;
    blockCount = count;
    return result;
  }

  // 링크 하나를 앱 요청으로. 문서 안 이동이면 null.
  function requestFor(anchor) {
    const href = anchor.getAttribute('href') || '';
    const block = anchor.closest('.madang-block');
    const open = anchor.getAttribute('data-open');
    if (open === 'block' && block) {
      return {type: 'block', id: block.getAttribute('data-block'), href: href};
    }
    if (open === 'run' && block) {
      return {type: 'run', n: block.getAttribute('data-run')};
    }
    if (IN_PAGE.test(href)) return null;
    return {type: 'open', href: href};
  }

  /**
   * 앱에 요청을 보낸다. `madang-app://<type>?<필드>`로 탐색하면 앱이 막고
   * 받는다. 테스트는 이 함수를 바꿔 끼워 요청을 모은다.
   *
   * @param {!Object<string, string>} request `type`과 필드.
   */
  function post(request) {
    const query = Object.keys(request).filter((key) => key !== 'type')
        .map((key) => {
          return encodeURIComponent(key) + '=' +
              encodeURIComponent(request[key]);
        }).join('&');
    root.location.href = SCHEME + request.type + (query ? '?' + query : '');
  }

  const api = {version: 1, render: render, post: post};

  root.document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    const anchor = event.target.closest && event.target.closest('a[href]');
    if (!anchor) return;
    const request = requestFor(anchor);
    if (!request) return;
    event.preventDefault();
    api.post(request);
  });

  // 더블클릭 = 열기. "열기"가 있는 블록은 어디를 두 번 눌러도 그 링크와 같다.
  root.document.addEventListener('dblclick', (event) => {
    const block = event.target.closest && event.target.closest('.madang-block');
    const head = block && block.querySelector('.madang-block-head');
    const anchor = head && head.querySelector('a.madang-block-open');
    if (anchor) api.post(requestFor(anchor));
  });

  root.madangApp = api;
})(window);
