/*
 * document.js - Madang 문서 렌더러.
 *
 * 마크다운(머리부, 표, 코드 블록), view 펜스, page.md 블록(요청·실행·결과·
 * 묻는 블록)을 HTML 문자열로 그린다.
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
  // page.md 블록 머리: <!-- bNN | 시각 | 역할 | key=value ... -->
  const BLOCK_HEAD = /^<!--[ \t]*(b\d+)[ \t]*\|[ \t]*([^|\n]*?)[ \t]*\|[ \t]*([\w-]+)[ \t]*(?:\|[ \t]*([^\n]*?))?[ \t]*-->[ \t]*\r?$/gm;
  const CLOCK = /T(\d\d:\d\d)/;
  const BLOCK_LABELS = {
    request: '요청',
    answer: '답',
    route: '라우팅',
    run: '실행',
    result: '결과',
    ask: '묻는 블록',
    doc: '문서',
    data: '데이터',
    view: '뷰',
    code: '코드',
    term: '터미널',
    site: '사이트',
  };
  // 접어서 보여 주는 블록 종류. 펼치면 본문이 보인다.
  const FOLDED_KINDS = ['route', 'run'];
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

  // 펜스의 data= 파일로 가는 "데이터" 링크. 앱은 이 링크로 데이터 탭을 연다.
  function dataLink(ref) {
    if (!ref.data || !isSafeLink(ref.data)) return '';
    return '<p class="madang-view-links"><a class="madang-view-data" href="' +
        escapeHtml(ref.data) + '" data-open="data">데이터</a></p>';
  }

  function viewFrame(ref, entry, tokens) {
    const srcdoc = viewDocument(entry.html, entry.data, tokens);
    return '<figure class="madang-view" data-view="' + escapeHtml(ref.name) +
        '" data-status="ok">' + dataLink(ref) +
        '<iframe class="madang-view-frame" ' +
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
        '</figcaption>' + dataLink(ref) + detail + errorList(entry.errors) +
        body + '</figure>\n';
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

  // ---------------------------------------------------------------- 블록

  function decodeValue(value) {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  // 머리 줄의 key=value. 값은 퍼센트 인코딩일 수 있다(공백이 든 제목 등).
  function blockAttrs(text) {
    const attrs = {};
    String(text || '').split(/\s+/).forEach((item) => {
      const eq = item.indexOf('=');
      if (eq > 0) attrs[item.slice(0, eq)] = decodeValue(item.slice(eq + 1));
    });
    return attrs;
  }

  // 본문을 첫 블록 머리 앞의 개요와 쓰인 순서대로의 블록으로 나눈다.
  function splitBlocks(body) {
    const heads = Array.from(body.matchAll(BLOCK_HEAD));
    if (!heads.length) return {overview: body, blocks: []};
    const blocks = heads.map((head, i) => {
      const start = head.index + head[0].length;
      const end = i + 1 < heads.length ? heads[i + 1].index : body.length;
      return {
        id: head[1],
        time: head[2],
        role: head[3],
        attrs: blockAttrs(head[4]),
        body: body.slice(start, end).trim(),
      };
    });
    return {overview: body.slice(0, heads[0].index), blocks: blocks};
  }

  // 역할과 머리 필드로 블록 종류를 정한다. 메시지가 아닌 역할은 그대로 쓴다.
  function blockKind(block) {
    switch (block.role) {
      case 'user':
        return block.attrs.answer ? 'answer' : 'request';
      case 'agent':
        return 'result';
      case 'router':
        return block.attrs.ask === 'true' ? 'ask' : 'route';
      default:
        return block.role;
    }
  }

  function dataAttributes(data) {
    return Object.keys(data).filter((key) => {
      return data[key] !== undefined && data[key] !== null && data[key] !== '';
    }).map((key) => {
      return ' data-' + key + '="' + escapeHtml(data[key]) + '"';
    }).join('');
  }

  function span(name, text) {
    if (!text) return '';
    return '<span class="madang-block-' + name + '">' + escapeHtml(text) +
        '</span>';
  }

  function openLink(href, kind) {
    return '<a class="madang-block-open" href="' + escapeHtml(href) +
        '" data-open="' + kind + '">열기</a>';
  }

  // 블록 컴포넌트 하나. 라우팅·실행은 접힌 <details>, 나머지는 <section>.
  function blockHtml(part) {
    const folded = FOLDED_KINDS.indexOf(part.data.kind) >= 0;
    const tag = folded ? 'details' : 'section';
    const head = folded ? 'summary' : 'header';
    const body = part.body ?
      '<div class="madang-block-body">' + part.body + '</div>' : '';
    return '<' + tag + ' class="madang-block"' + dataAttributes(part.data) +
        '><' + head + ' class="madang-block-head">' +
        span('label', part.label) + span('title', part.title) +
        span('meta', part.meta) + (part.time || '') + (part.open || '') +
        '</' + head + '>' + body + '</' + tag + '>\n';
  }

  function renderBlock(block, markdown) {
    const kind = blockKind(block);
    const attrs = block.attrs;
    const meta = [];
    if (attrs.target && attrs.target !== 'page') meta.push('→ ' + attrs.target);
    if (attrs.run) meta.push('run ' + attrs.run);
    const clock = CLOCK.exec(block.time);
    const parts = splitFrontMatter(block.body);
    const head =
        parts.frontMatter === null ? '' : frontMatterHtml(parts.frontMatter);
    return blockHtml({
      data: {
        block: block.id,
        kind: kind,
        role: block.role,
        run: attrs.run,
        pending: attrs.pending,
      },
      label: BLOCK_LABELS[kind] || kind,
      title: attrs.title,
      meta: meta.join(' · '),
      time: clock ? '<time class="madang-block-time" datetime="' +
          escapeHtml(block.time) + '">' + clock[1] + '</time>' : '',
      open: attrs.file && isSafeLink(attrs.file) ?
          openLink(attrs.file, 'block') : '',
      body: head + markdown.parse(parts.body),
    });
  }

  function renderRun(run) {
    const n = String(run.n);
    const files = Array.isArray(run.files) ? run.files : [];
    const list = files.length ? '<ul class="madang-block-files">' +
        files.map((file) => '<li><code>' + escapeHtml(file) + '</code></li>')
            .join('') + '</ul>' : '';
    return blockHtml({
      data: {kind: 'run', run: n, status: run.status},
      label: BLOCK_LABELS.run + ' ' + n,
      title: run.title,
      meta: [run.summary, run.status].filter(Boolean).join(' · '),
      open: openLink('#run-' + n, 'run'),
      body: list,
    });
  }

  // 개요 뒤에 블록을 쓰인 순서대로 그린다. 실행은 그 실행을 일으킨 블록
  // (`after`) 바로 뒤에, 짝이 없으면 끝에 둔다.
  function renderBody(body, context, markdown) {
    const parts = splitBlocks(body);
    const runs = Array.isArray(context.runs) ? context.runs : [];
    const ids = parts.blocks.map((block) => block.id);
    let html = markdown.parse(parts.overview);
    parts.blocks.forEach((block) => {
      html += renderBlock(block, markdown);
      runs.filter((run) => run.after === block.id).forEach((run) => {
        html += renderRun(run);
      });
    });
    runs.filter((run) => ids.indexOf(run.after) < 0).forEach((run) => {
      html += renderRun(run);
    });
    return html;
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
   * "broken", 항목 없음)이면 데이터를 표로 대체한다. `data=`가 있으면
   * 그 파일로 가는 "데이터" 링크를 붙인다.
   *
   * page.md 블록 머리 주석(`<!-- bNN | 시각 | 역할 | key=value -->`)은 블록
   * 컴포넌트가 된다: user는 요청(`answer=`면 답), agent는 결과, router는
   * 라우팅(`ask=true`면 묻는 블록). 그 밖의 역할(doc, data, view 등)은 그
   * 이름의 블록이고 `file=`이 있으면 "열기" 링크를 단다. 값은 퍼센트
   * 인코딩일 수 있다.
   *
   * @param {string} markdown 마크다운 원문. 맨 앞 `---` 머리부는 떼어 낸다.
   * @param {{views: (!Object<string, {status: string, html: (string|undefined),
   *     data: *, errors: (!Array<{path: string, message: string}>|undefined),
   *     message: (string|undefined)}>|undefined),
   *     tokens: (!Object<string, string>|undefined),
   *     runs: (!Array<{n: number, after: (string|undefined),
   *     title: (string|undefined), summary: (string|undefined),
   *     status: (string|undefined),
   *     files: (!Array<string>|undefined)}>|undefined)}=} context `views`는
   *     listViews()의 `key`별 해석 결과, `tokens`는 `bg`·`text`·`accent`·
   *     `font`·`radius` 값(`--app-*`로 주입), `runs`는 실행 기록(`after`
   *     블록 뒤에 접힌 실행 블록으로 그린다).
   * @return {{html: string, frontMatter: ?string,
   *     views: !Array<!Object>}} `madang-document` 요소 하나로 감싼 HTML,
   *     머리부 원문, 문서의 view 참조(listViews()와 같다).
   */
  function renderDocument(markdown, context) {
    const parts = splitFrontMatter(markdown);
    const options = context || {};
    const body = renderBody(parts.body, options, createMarkdown(options));
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

  // 문서 바탕도 뷰어 iframe과 같은 앱 토큰을 따른다. 주지 않았거나 안전하지
  // 않은 토큰은 지워 document.css의 대체값이 쓰이게 한다.
  function applyTokens(element, tokens) {
    TOKEN_NAMES.forEach((name) => {
      const value = tokens && tokens[name];
      if (typeof value === 'string' && SAFE_TOKEN.test(value)) {
        element.style.setProperty('--app-' + name, value);
      } else {
        element.style.removeProperty('--app-' + name);
      }
    });
  }

  /**
   * renderDocument() 결과를 요소에 넣고 뷰어 iframe 높이를 맞춘다.
   * `context.tokens`는 문서의 html 요소에도 `--app-*`로 둔다. 앱 문서 탭과
   * 게시 페이지가 이 함수를 같이 쓰므로 같은 토큰이면 같은 모양이다.
   *
   * @param {!Element} target 문서를 넣을 요소. 기존 내용은 지운다.
   * @param {string} markdown 마크다운 원문.
   * @param {!Object=} context renderDocument()와 같다.
   * @return {!Object} renderDocument()의 결과.
   */
  function mountDocument(target, markdown, context) {
    const result = renderDocument(markdown, context);
    applyTokens(target.ownerDocument.documentElement,
        context && context.tokens);
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
