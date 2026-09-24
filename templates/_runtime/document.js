/*
 * document.js - Madang 문서 렌더러.
 *
 * 마크다운(머리부, 표, 코드 블록)과 view 펜스를 HTML 문자열로 그린다.
 * DOM 없이 돌아서 앱 문서 탭(WebView)과 게시(Node)가 같은 함수를 부른다.
 * 마크다운 해석은 같은 폴더의 vendor/marked.umd.js(MIT)가 맡는다.
 * 네트워크에 접근하지 않는다. 원격 이미지는 불러오지 않고 링크로 보여 준다.
 */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./vendor/marked.umd.js'));
  } else {
    root.madangDocument = factory(root.marked);
  }
})(typeof self !== 'undefined' ? self : globalThis, (markedLib) => {
  'use strict';

  const VIEW_LANG = 'view';
  const FRONT_MATTER = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/;
  const URL_SCHEME = /^([a-z][a-z0-9+.-]*):/i;
  const LINK_SCHEMES = ['http', 'https', 'mailto'];
  // 뷰어 iframe 안으로 주입하는 앱 토큰. 뷰어는 정의하거나 덮어쓰지 못한다.
  const TOKEN_NAMES = ['bg', 'text', 'accent', 'font', 'radius'];
  const SAFE_TOKEN = /^[^;{}<>\\]*$/;
  const VIEW_CSP = [
    'default-src \'none\'',
    'script-src \'unsafe-inline\'',
    'style-src \'unsafe-inline\'',
    'img-src data:',
    'font-src data:',
    'base-uri \'none\'',
    'form-action \'none\'',
  ].join('; ');
  // 뷰어 문서 높이를 부모에게 알린다. mountDocument()가 받아 iframe을 맞춘다.
  const RESIZE_SCRIPT = '<script>(function(){function send(){' +
      'parent.postMessage({source:"madang-view",type:"resize",' +
      'height:document.documentElement.scrollHeight},"*");}' +
      'addEventListener("load",send);if(window.ResizeObserver){' +
      'new ResizeObserver(send).observe(document.documentElement);}' +
      '})();</script>';
  const FALLBACK_MESSAGES = {
    missing: (name) => `뷰어 "${name}"를 찾을 수 없어 데이터를 표로 보여 줍니다.`,
    broken: (name) => `뷰어 "${name}" 연결이 끊겨 데이터를 표로 보여 줍니다.`,
    invalid: (name) =>
      `데이터가 뷰어 "${name}" 스키마와 맞지 않아 표로 보여 줍니다.`,
  };

  // ---------------------------------------------------------------- 문자열

  const HTML_ESCAPES = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    '\'': '&#39;',
  };

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
  }

  function isPlainObject(value) {
    return value !== null && typeof value === 'object' &&
        !Array.isArray(value);
  }

  // ---------------------------------------------------------------- 머리부

  function splitFrontMatter(markdown) {
    const text = String(markdown || '');
    const match = FRONT_MATTER.exec(text);
    if (!match) return {frontMatter: null, body: text};
    return {frontMatter: match[1], body: text.slice(match[0].length)};
  }

  function frontMatterHtml(frontMatter) {
    return '<details class="madang-frontmatter"><summary>머리부</summary>' +
        '<pre><code class="language-yaml">' + escapeHtml(frontMatter) +
        '</code></pre></details>\n';
  }

  // ---------------------------------------------------------------- 링크

  // 브라우저는 URL의 공백·제어 문자를 무시하므로 검사 전에 지운다.
  function stripControl(url) {
    return Array.from(String(url)).filter((c) => {
      const code = c.charCodeAt(0);
      return code > 0x20 && code !== 0x7f;
    }).join('');
  }

  function schemeOf(url) {
    const match = URL_SCHEME.exec(stripControl(url));
    return match ? match[1].toLowerCase() : null;
  }

  function isSafeLink(href) {
    const scheme = schemeOf(href);
    return scheme === null || LINK_SCHEMES.indexOf(scheme) >= 0;
  }

  // 문서 옆 파일(상대 경로)과 data:image만 불러온다.
  function isLocalImage(src) {
    const clean = stripControl(src);
    if (clean.indexOf('//') === 0) return false;
    const scheme = schemeOf(clean);
    return scheme === null || /^data:image\//i.test(clean);
  }

  // ---------------------------------------------------------------- view 펜스

  // "view resume/basic@1a2b data=./base.json" -> 참조. view 펜스가 아니면 null.
  function parseViewInfo(info) {
    const words = String(info || '').trim().split(/\s+/);
    if (words[0] !== VIEW_LANG) return null;
    const target = words[1] || '';
    const at = target.indexOf('@');
    let data = null;
    words.slice(2).forEach((word) => {
      if (word.indexOf('data=') === 0) data = word.slice('data='.length);
    });
    return {
      key: words.slice(1).join(' '),
      name: at < 0 ? target : target.slice(0, at),
      pin: at < 0 ? null : target.slice(at + 1) || null,
      data: data,
    };
  }

  // 호스트가 주지 않았거나 안전하지 않은 토큰은 initial로 비워 뷰어가
  // 정의한 값도 쓰이지 않게 한다(var()의 대체값이 쓰인다).
  function tokenStyle(tokens) {
    const declarations = TOKEN_NAMES.map((name) => {
      const value = tokens && tokens[name];
      const safe = typeof value === 'string' && SAFE_TOKEN.test(value);
      return `--app-${name}:${safe ? value : 'initial'} !important;`;
    });
    return '<style id="madang-app-tokens">:root:root:root{' +
        declarations.join('') + '}</style>';
  }

  function dataScript(data) {
    const json = JSON.stringify(data === undefined ? null : data)
        .replace(/</g, '\\u003c');
    return '<script type="application/json" id="madang-view-data">' + json +
        '</script>';
  }

  // CSP·데이터·높이 알림은 맨 앞에, 앱 토큰은 맨 뒤에 넣어 뷰어보다 이긴다.
  function viewDocument(html, data, tokens) {
    const head = '<meta http-equiv="Content-Security-Policy" content="' +
        VIEW_CSP + '">' + dataScript(data) + RESIZE_SCRIPT;
    const headTag = /<head(\s[^>]*)?>/i.exec(html);
    const htmlTag = /<html(\s[^>]*)?>/i.exec(html);
    let out;
    if (headTag) {
      const end = headTag.index + headTag[0].length;
      out = html.slice(0, end) + head + html.slice(end);
    } else if (htmlTag) {
      const end = htmlTag.index + htmlTag[0].length;
      out = html.slice(0, end) + '<head>' + head + '</head>' + html.slice(end);
    } else {
      out = '<head>' + head + '</head>' + html;
    }
    return out + tokenStyle(tokens);
  }

  function viewFrame(ref, entry, tokens) {
    const srcdoc = viewDocument(entry.html, entry.data, tokens);
    return '<figure class="madang-view" data-view="' + escapeHtml(ref.name) +
        '" data-status="ok"><iframe class="madang-view-frame" ' +
        'sandbox="allow-scripts" title="' + escapeHtml(ref.name) +
        '" srcdoc="' + escapeHtml(srcdoc) + '"></iframe></figure>\n';
  }

  function errorList(errors) {
    if (!Array.isArray(errors) || !errors.length) return '';
    const items = errors.map((e) => {
      const path = e && e.path ? e.path : '(전체)';
      return '<li><code>' + escapeHtml(path) + '</code> ' +
          escapeHtml(e && e.message ? e.message : '') + '</li>';
    });
    return '<ul class="madang-view-errors">' + items.join('') + '</ul>';
  }

  function viewFallback(ref, entry) {
    const status = FALLBACK_MESSAGES[entry.status] ? entry.status : 'broken';
    const detail = entry.message ?
      '<p class="madang-view-detail">' + escapeHtml(entry.message) + '</p>' :
      '';
    const body = entry.data === undefined || entry.data === null ?
      '<p class="madang-view-empty">데이터 없음</p>' : dataTable(entry.data);
    return '<figure class="madang-view madang-view-fallback" data-view="' +
        escapeHtml(ref.name) + '" data-status="' + status + '">' +
        '<figcaption>' + escapeHtml(FALLBACK_MESSAGES[status](ref.name)) +
        '</figcaption>' + detail + errorList(entry.errors) + body +
        '</figure>\n';
  }

  function renderView(ref, context) {
    const views = (context && context.views) || {};
    const entry = Object.prototype.hasOwnProperty.call(views, ref.key) ?
      views[ref.key] : {status: 'missing'};
    if (entry.status === 'ok' && typeof entry.html === 'string') {
      return viewFrame(ref, entry, context && context.tokens);
    }
    return viewFallback(ref, entry);
  }

  // ---------------------------------------------------------------- 데이터 표

  function dataTable(value) {
    if (Array.isArray(value)) return arrayTable(value);
    if (isPlainObject(value)) return objectTable(value);
    return '<span class="madang-data-value">' + escapeHtml(scalarText(value)) +
        '</span>';
  }

  function scalarText(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  function objectTable(object) {
    const rows = Object.keys(object).map((key) => {
      return '<tr><th scope="row">' + escapeHtml(key) + '</th><td>' +
          dataTable(object[key]) + '</td></tr>';
    });
    return '<table class="madang-data"><tbody>' + rows.join('') +
        '</tbody></table>';
  }

  // 객체 배열은 열 머리글이 있는 표, 그 외 배열은 번호 붙은 행으로 그린다.
  function arrayTable(items) {
    if (items.length && items.every(isPlainObject)) {
      const columns = [];
      items.forEach((item) => {
        Object.keys(item).forEach((key) => {
          if (columns.indexOf(key) < 0) columns.push(key);
        });
      });
      const head = '<thead><tr><th>#</th>' + columns.map((c) => {
        return '<th scope="col">' + escapeHtml(c) + '</th>';
      }).join('') + '</tr></thead>';
      const rows = items.map((item, i) => {
        return '<tr><th scope="row">' + i + '</th>' + columns.map((c) => {
          return '<td>' + dataTable(item[c]) + '</td>';
        }).join('') + '</tr>';
      });
      return '<table class="madang-data">' + head + '<tbody>' +
          rows.join('') + '</tbody></table>';
    }
    const rows = items.map((item, i) => {
      return '<tr><th scope="row">' + i + '</th><td>' + dataTable(item) +
          '</td></tr>';
    });
    return '<table class="madang-data"><tbody>' + rows.join('') +
        '</tbody></table>';
  }

  // ---------------------------------------------------------------- 마크다운

  // 원문 HTML은 글자로, 위험한 링크는 글자로, 원격 이미지는 링크로 바꾼다.
  function createMarkdown(context) {
    const instance = new markedLib.Marked({gfm: true});
    instance.use({
      renderer: {
        code(token) {
          const ref = parseViewInfo(token.lang);
          return ref ? renderView(ref, context) : false;
        },
        html(token) {
          const text = escapeHtml(token.text);
          return token.block ? '<p>' + text.trim() + '</p>\n' : text;
        },
        link(token) {
          if (isSafeLink(token.href)) return false;
          return this.parser.parseInline(token.tokens);
        },
        image(token) {
          if (isLocalImage(token.href)) return false;
          const label = escapeHtml(token.text || token.href);
          if (!isSafeLink(token.href)) return label;
          return '<a class="madang-remote-image" href="' +
              escapeHtml(token.href) + '">' + label + '</a>';
        },
      },
    });
    return instance;
  }

  /**
   * 문서에 있는 view 펜스를 순서대로 찾는다. 같은 참조는 한 번만 담는다.
   * 호스트는 이 목록으로 뷰어와 데이터를 미리 해석해 `context.views`를
   * 채운다.
   *
   * @param {string} markdown 마크다운 원문(머리부 포함 가능).
   * @return {!Array<{key: string, name: string, pin: ?string,
   *     data: ?string}>} 펜스 참조. `key`가 `context.views`의 키다.
   */
  function listViews(markdown) {
    const instance = new markedLib.Marked({gfm: true});
    const tokens = instance.lexer(splitFrontMatter(markdown).body);
    const found = [];
    instance.walkTokens(tokens, (token) => {
      if (token.type !== 'code') return;
      const ref = parseViewInfo(token.lang);
      if (ref && !found.some((f) => f.key === ref.key)) found.push(ref);
    });
    return found;
  }

  /**
   * 마크다운 문서를 HTML 조각으로 그린다. 앱 문서 탭과 게시가 함께 쓰는
   * 유일한 렌더러다.
   *
   * 정보 문자열이 `view <이름>[@해시] data=<경로>`인 코드 펜스는
   * `context.views[key]`로 그린다. 상태가 "ok"면 `allow-scripts`만 있는
   * sandbox iframe에 뷰어 HTML·데이터·앱 토큰을 넣고, 그 밖("invalid",
   * "broken", 항목 없음)이면 데이터를 표로 대체한다.
   *
   * @param {string} markdown 마크다운 원문. 맨 앞 `---` 머리부는 떼어 낸다.
   * @param {{views: (!Object<string, {status: string, html: (string|undefined),
   *     data: *, errors: (!Array<{path: string, message: string}>|undefined),
   *     message: (string|undefined)}>|undefined),
   *     tokens: (!Object<string, string>|undefined)}=} context `views`는
   *     listViews()의 `key`별 해석 결과, `tokens`는 `bg`·`text`·`accent`·
   *     `font`·`radius` 값(`--app-*`로 주입).
   * @return {{html: string, frontMatter: ?string,
   *     views: !Array<!Object>}} `madang-document` 요소 하나로 감싼 HTML,
   *     머리부 원문, 문서의 view 참조(listViews()와 같다).
   */
  function renderDocument(markdown, context) {
    const parts = splitFrontMatter(markdown);
    const body = createMarkdown(context || {}).parse(parts.body);
    const head =
        parts.frontMatter === null ? '' : frontMatterHtml(parts.frontMatter);
    return {
      html: '<div class="madang-document">' + head + body + '</div>',
      frontMatter: parts.frontMatter,
      views: listViews(markdown),
    };
  }

  // ---------------------------------------------------------------- 브라우저

  const resizeListeners = new WeakSet();

  // 뷰어가 알린 높이로 그 iframe만 맞춘다. 창마다 한 번만 듣는다.
  function listenForResize(view) {
    if (!view || resizeListeners.has(view)) return;
    resizeListeners.add(view);
    view.addEventListener('message', (event) => {
      const msg = event.data;
      if (!msg || msg.source !== 'madang-view' || msg.type !== 'resize') {
        return;
      }
      const height = Number(msg.height);
      if (!(height > 0)) return;
      const frames = view.document.querySelectorAll('iframe.madang-view-frame');
      Array.prototype.forEach.call(frames, (frame) => {
        if (frame.contentWindow === event.source) {
          frame.style.height = Math.ceil(height) + 'px';
        }
      });
    });
  }

  /**
   * renderDocument() 결과를 요소에 넣고 뷰어 iframe 높이를 맞춘다.
   *
   * @param {!Element} target 문서를 넣을 요소. 기존 내용은 지운다.
   * @param {string} markdown 마크다운 원문.
   * @param {!Object=} context renderDocument()와 같다.
   * @return {!Object} renderDocument()의 결과.
   */
  function mountDocument(target, markdown, context) {
    const result = renderDocument(markdown, context);
    target.innerHTML = result.html;
    listenForResize(target.ownerDocument.defaultView);
    return result;
  }

  return {
    version: 1,
    renderDocument: renderDocument,
    listViews: listViews,
    mountDocument: mountDocument,
  };
});
