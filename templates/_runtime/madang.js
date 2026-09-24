/*
 * madang.js - Madang 화면용 템플릿 런타임.
 *
 * WebView 안에서 실행된다. 슬롯 데이터로 템플릿(data-bind 표시가 있는
 * page.html)을 그리고, 렌더된 값이 어느 슬롯에서 왔는지 추적하며, 편집 모드의
 * 요소 선택을 처리하고, 교체 가능한 브리지로 호스트 앱과 통신한다.
 * 의존성과 네트워크 접근이 없다.
 */
(function(global) {
  'use strict';

  if (global.madang && global.madang.__runtime) return;

  const doc = global.document;
  const ATTR_PATH = 'data-madang-path';
  const ATTR_SLOT = 'data-madang-slot';
  const ATTR_TPL = 'data-madang-tpl';
  const TEMPLATE_SOURCE = 'template';
  const CLASS_SELECTED = 'madang-selected';
  const CLASS_HOVER = 'madang-hover';

  const state = {
    template: null,
    slotOrder: [],
    data: {},
    merged: undefined,
    origin: new Map(),
    theme: {},
    themeVars: [],
    mode: 'view',
    root: null,
    snapshot: null,
    selection: [],
    hoverPath: null,
    ready: false,
    bridge: null,
    markdownRenderer: null,
  };

  // ---------------------------------------------------------------- 경로

  function parsePath(text) {
    const segs = [];
    const re = /([^.[\]]+)|\[(\d+)\]/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m[1] !== undefined) segs.push(m[1]);
      else segs.push(Number(m[2]));
    }
    return segs;
  }

  function formatPath(segs) {
    let out = '';
    for (let i = 0; i < segs.length; i++) {
      const s = segs[i];
      if (typeof s === 'number') out += '[' + s + ']';
      else out += (out ? '.' : '') + s;
    }
    return out;
  }

  function getAt(value, segs) {
    let cur = value;
    for (let i = 0; i < segs.length; i++) {
      if (cur === null || cur === undefined) return undefined;
      cur = cur[segs[i]];
    }
    return cur;
  }

  function isPlainObject(v) {
    return v !== null && typeof v === 'object' && !Array.isArray(v);
  }

  function clone(v) {
    if (Array.isArray(v)) return v.map(clone);
    if (isPlainObject(v)) {
      const o = {};
      Object.keys(v).forEach((k) => {
        o[k] = clone(v[k]);
      });
      return o;
    }
    return v;
  }

  // ---------------------------------------------------------------- 병합

  function forgetSubtree(origin, prefix) {
    if (prefix === '') {
      origin.clear();
      return;
    }
    origin.forEach((_, key) => {
      if (key === prefix || key.indexOf(prefix + '.') === 0 ||
          key.indexOf(prefix + '[') === 0) {
        origin.delete(key);
      }
    });
  }

  function recordSubtree(origin, value, segs, slot) {
    origin.set(formatPath(segs), slot);
    if (Array.isArray(value)) {
      value.forEach((item, i) => {
        recordSubtree(origin, item, segs.concat(i), slot);
      });
    } else if (isPlainObject(value)) {
      Object.keys(value).forEach((k) => {
        recordSubtree(origin, value[k], segs.concat(k), slot);
      });
    }
  }

  // 객체는 깊게 합치고, 그 외(배열 포함)는 통째로 바꾼다.
  function combine(prev, next, slot, segs, origin) {
    if (next === undefined) return prev;
    if (isPlainObject(prev) && isPlainObject(next)) {
      const out = {};
      Object.keys(prev).forEach((k) => {
        out[k] = prev[k];
      });
      Object.keys(next).forEach((k) => {
        out[k] = combine(prev[k], next[k], slot, segs.concat(k), origin);
      });
      origin.set(formatPath(segs), slot);
      return out;
    }
    forgetSubtree(origin, formatPath(segs));
    const copy = clone(next);
    recordSubtree(origin, copy, segs, slot);
    return copy;
  }

  function slotNames(template) {
    const slots = template && template.slots;
    if (!slots) return [];
    if (Array.isArray(slots)) {
      return slots.map((s) => (typeof s === 'string' ? s : s.name));
    }
    return Object.keys(slots);
  }

  function recompute() {
    const order = state.slotOrder.slice();
    Object.keys(state.data).forEach((k) => {
      if (order.indexOf(k) < 0) order.push(k);
    });
    const origin = new Map();
    let merged;
    order.forEach((slot) => {
      if (state.data[slot] !== undefined) {
        merged = combine(merged, state.data[slot], slot, [], origin);
      }
    });
    state.merged = merged;
    state.origin = origin;
  }

  // 템플릿 고정 텍스트의 경로는 "template:<위치>" 꼴이다.
  function isTemplatePath(path) {
    return typeof path === 'string' &&
        path.indexOf(TEMPLATE_SOURCE + ':') === 0;
  }

  /**
   * 경로의 값을 공급한 슬롯을 돌려준다. 기록된 가장 가까운 상위 경로가
   * 우선하며, 템플릿 고정 텍스트의 출처는 "template"이다.
   *
   * @param {string|!Array<string|number>} path 데이터 경로 또는 그 마디 배열.
   * @return {?string} 슬롯 이름, "template", 일치하는 것이 없으면 null.
   */
  function sourceOf(path) {
    if (isTemplatePath(path)) return TEMPLATE_SOURCE;
    const segs = typeof path === 'string' ? parsePath(path) : path;
    for (let n = segs.length; n >= 0; n--) {
      const key = formatPath(segs.slice(0, n));
      if (state.origin.has(key)) return state.origin.get(key);
    }
    return null;
  }

  // ---------------------------------------------------------------- 렌더

  function rootElement() {
    return doc.querySelector('[data-madang-root]') || doc.body;
  }

  function takeSnapshot(root) {
    markTemplateText(root, []);
    const frag = doc.createDocumentFragment();
    Array.prototype.forEach.call(root.childNodes, (n) => {
      frag.appendChild(n.cloneNode(true));
    });
    return frag;
  }

  function hasOwnText(el) {
    for (let n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3 && n.nodeValue.trim() !== '') return true;
    }
    return false;
  }

  // 템플릿 고정 텍스트를 가진 요소에 안정적인 위치 키를 붙인다.
  function markTemplateText(el, chain) {
    Array.prototype.forEach.call(el.children, (child, i) => {
      const here = chain.concat(i);
      if (child.tagName === 'STYLE' || child.tagName === 'SCRIPT') return;
      if (hasOwnText(child) && !child.hasAttribute('data-bind')) {
        child.setAttribute(ATTR_TPL, (child.id || here.join('.')));
      }
      markTemplateText(child, here);
    });
  }

  function resolve(expr, scope) {
    expr = expr.trim();
    if (expr.charAt(0) === '.') {
      return scope.concat(parsePath(expr.slice(1)));
    }
    const segs = parsePath(expr);
    const slot = segs.shift();
    if (state.slotOrder.length && state.slotOrder.indexOf(slot) < 0 &&
        !(slot in state.data)) {
      throw new Error('unknown slot "' + slot + '" in "' + expr + '"');
    }
    return segs;
  }

  function toText(v) {
    if (v === null || v === undefined) return '';
    if (Array.isArray(v)) return v.map(toText).join(', ');
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }

  function truthy(v) {
    if (Array.isArray(v)) return v.length > 0;
    if (isPlainObject(v)) return Object.keys(v).length > 0;
    return v !== null && v !== undefined && v !== false && v !== '' &&
        v !== 0;
  }

  // data-where="status=doing|todo" or "state!=superseded"
  function matchesWhere(item, where) {
    if (!where) return true;
    return where.split(';').every((clause) => {
      const m = /^\s*([^!=\s]+)\s*(!?=)\s*(.*?)\s*$/.exec(clause);
      if (!m) return true;
      const actual = toText(getAt(item, parsePath(m[1])));
      const hit = m[3].split('|').map((s) => s.trim()).indexOf(actual) >= 0;
      return m[2] === '=' ? hit : !hit;
    });
  }

  const UNSAFE_URL = /^\s*(javascript|vbscript|data:text\/html)/i;
  const URL_ATTRS = ['href', 'src', 'action', 'formaction', 'poster',
    'xlink:href'];
  const ATTR_BINDING_PREFIX = 'data-attr-';

  function setPath(el, segs) {
    const path = formatPath(segs);
    el.setAttribute(ATTR_PATH, path);
    el.setAttribute(ATTR_SLOT, sourceOf(segs) || '');
  }

  function valueAt(expr, scope) {
    return getAt(state.merged, resolve(expr, scope));
  }

  function processElement(el, scope) {
    if (el.hasAttribute('data-each')) {
      expandEach(el, scope);
      return;
    }
    if (!passesConditions(el, scope)) {
      el.remove();
      return;
    }
    const attrPath = bindAttributes(el, scope);
    if (el.hasAttribute('data-bind')) {
      bindText(el, scope);
      return;
    }
    if (attrPath && !el.hasAttribute(ATTR_PATH)) setPath(el, attrPath);
    tagTemplateText(el, scope);
    Array.prototype.slice.call(el.children).forEach((child) => {
      processElement(child, scope);
    });
  }

  // data-if는 값이 참일 때, data-unless는 아닐 때 요소를 남긴다.
  function passesConditions(el, scope) {
    if (el.hasAttribute('data-if') &&
        !truthy(valueAt(el.getAttribute('data-if'), scope))) {
      return false;
    }
    if (el.hasAttribute('data-unless') &&
        truthy(valueAt(el.getAttribute('data-unless'), scope))) {
      return false;
    }
    return true;
  }

  // data-attr-<name> 속성을 채우고 처음 바인딩된 경로를 돌려준다.
  function bindAttributes(el, scope) {
    let firstPath = null;
    Array.prototype.slice.call(el.attributes).forEach((a) => {
      if (a.name.indexOf(ATTR_BINDING_PREFIX) !== 0) return;
      const name = a.name.slice(ATTR_BINDING_PREFIX.length);
      if (/^on/i.test(name)) return;
      const segs = resolve(a.value, scope);
      const v = getAt(state.merged, segs);
      if (v === null || v === undefined || v === false) {
        el.removeAttribute(name);
        return;
      }
      const text = toText(v);
      if (isUnsafeUrl(name, text)) {
        el.removeAttribute(name);
        return;
      }
      el.setAttribute(name, text);
      if (!firstPath) firstPath = segs;
    });
    return firstPath;
  }

  function isUnsafeUrl(attrName, value) {
    return URL_ATTRS.indexOf(attrName) >= 0 && UNSAFE_URL.test(value);
  }

  function bindText(el, scope) {
    const segs = resolve(el.getAttribute('data-bind'), scope);
    el.textContent = toText(getAt(state.merged, segs));
    setPath(el, segs);
    el.removeAttribute(ATTR_TPL);
  }

  // 템플릿 고정 텍스트에 "template:<위치>[@범위]" 경로를 붙인다.
  function tagTemplateText(el, scope) {
    if (!el.hasAttribute(ATTR_TPL)) return;
    if (!el.hasAttribute(ATTR_PATH)) {
      const key = TEMPLATE_SOURCE + ':' + el.getAttribute(ATTR_TPL) +
          (scope.length ? '@' + formatPath(scope) : '');
      el.setAttribute(ATTR_PATH, key);
      el.setAttribute(ATTR_SLOT, TEMPLATE_SOURCE);
    }
    el.removeAttribute(ATTR_TPL);
  }

  function expandEach(el, scope) {
    const segs = resolve(el.getAttribute('data-each'), scope);
    const list = getAt(state.merged, segs);
    const where = el.getAttribute('data-where');
    const parent = el.parentNode;
    if (Array.isArray(list)) {
      list.forEach((item, i) => {
        if (!matchesWhere(item, where)) return;
        const itemSegs = segs.concat(i);
        const copy = el.cloneNode(true);
        copy.removeAttribute('data-each');
        copy.removeAttribute('data-where');
        parent.insertBefore(copy, el);
        if (!copy.hasAttribute('data-bind')) setPath(copy, itemSegs);
        processElement(copy, itemSegs);
      });
    }
    el.remove();
  }

  function applyTheme(theme) {
    const style = doc.documentElement.style;
    state.themeVars.forEach((name) => {
      style.removeProperty(name);
    });
    state.themeVars = [];
    const flat = flattenTheme(theme);
    Object.keys(flat).forEach((key) => {
      const name = '--' + key.replace(/[^a-zA-Z0-9]+/g, '-');
      style.setProperty(name, cssValue(key, flat[key]));
      state.themeVars.push(name);
    });
  }

  // {color: {accent: x}} 는 {'color.accent': x}가 된다.
  function flattenTheme(theme) {
    const flat = {};
    (function walk(obj, prefix) {
      Object.keys(obj || {}).forEach((k) => {
        const key = prefix ? prefix + '.' + k : k;
        if (isPlainObject(obj[k])) walk(obj[k], key);
        else flat[key] = obj[k];
      });
    })(theme, '');
    return flat;
  }

  // 크기가 숫자만 있으면 px 단위를 붙인다.
  function cssValue(key, value) {
    if (typeof value === 'number' && /size|width|gap|radius/.test(key)) {
      return value + 'px';
    }
    return String(value);
  }

  function paint() {
    const root = state.root;
    while (root.firstChild) root.removeChild(root.firstChild);
    root.appendChild(state.snapshot.cloneNode(true));
    Array.prototype.slice.call(root.children).forEach((child) => {
      processElement(child, []);
    });
    applySelectionClasses();
  }

  /**
   * 슬롯 데이터와 테마로 템플릿을 그린다. 실패는 예외를 던지지 않고
   * 호스트에 "error" 메시지로 알린다.
   *
   * @param {?Object} template `{name, version, slots, html?}`. `slots`는
   *     이름 배열, `{name}` 배열, 또는 순서 있는 객체다. `html`을 주면
   *     현재 마크업을 바꾼다.
   * @param {?Object} data 슬롯 이름에서 JSON 값으로의 대응.
   * @param {?Object} theme 중첩된 스타일 변수. 예: `{color: {accent}}`.
   * @param {string=} mode "view" 또는 "edit". 없으면 현재 모드를 유지한다.
   * @return {boolean} 렌더 성공 여부.
   */
  function render(template, data, theme, mode) {
    try {
      if (mode !== undefined && mode !== 'view' && mode !== 'edit') {
        throw new Error('unknown mode "' + mode + '"');
      }
      ensureStyle();
      state.template = template || {};
      state.slotOrder = slotNames(state.template);
      state.data = clone(data || {});
      state.theme = theme || {};
      state.root = rootElement();
      if (typeof state.template.html === 'string') {
        state.root.innerHTML = state.template.html;
        state.snapshot = takeSnapshot(state.root);
      } else if (!state.snapshot) {
        state.snapshot = takeSnapshot(state.root);
      }
      recompute();
      applyTheme(state.theme);
      paint();
      state.selection = state.selection.filter((p) => {
        return elementsFor(p).length > 0;
      });
      applySelectionClasses();
      setMode(mode || state.mode);
      return true;
    } catch (err) {
      reportError(err);
      return false;
    }
  }

  // ---------------------------------------------------------------- 데이터 편집

  function setAt(obj, segs, value) {
    let cur = obj;
    for (let i = 0; i < segs.length - 1; i++) {
      const s = segs[i];
      if (cur[s] === null || typeof cur[s] !== 'object') {
        cur[s] = typeof segs[i + 1] === 'number' ? [] : {};
      }
      cur = cur[s];
    }
    cur[segs[segs.length - 1]] = value;
  }

  /**
   * 값 하나를 바꾸고 즉시 다시 그린다.
   *
   * @param {string} path 데이터 경로. 예: `work[1].company`.
   * @param {*} value 새 값. 복사해서 쓴다.
   * @param {string=} slot 값을 쓸 슬롯. 기본은 현재 값을 공급한
   *     슬롯이고, 없으면 데이터가 있는 첫 슬롯이다.
   * @return {?{slot: string, path: string}} 값을 쓴 위치. 실패하면
   *     null.
   */
  function patchData(path, value, slot) {
    try {
      if (isTemplatePath(path)) {
        throw new Error(
            'fixed template text cannot be patched as data: "' + path + '"');
      }
      const segs = parsePath(path);
      if (!segs.length) throw new Error('empty path');
      const target = slot || sourceOf(segs) || firstSlotWithData() ||
          state.slotOrder[0];
      if (!target) throw new Error('no slot to patch');
      if (!isPlainObject(state.data[target])) state.data[target] = {};
      setAt(state.data[target], segs, clone(value));
      recompute();
      paint();
      return {slot: target, path: formatPath(segs)};
    } catch (err) {
      reportError(err);
      return null;
    }
  }

  function firstSlotWithData() {
    return state.slotOrder.filter((s) => state.data[s] !== undefined)[0];
  }

  // ---------------------------------------------------------------- 선택

  function elementsFor(path) {
    if (!state.root) return [];
    const all = state.root.querySelectorAll('[' + ATTR_PATH + ']');
    return Array.prototype.filter.call(all, (el) => {
      return el.getAttribute(ATTR_PATH) === path;
    });
  }

  function applySelectionClasses() {
    if (!state.root) return;
    const selected = state.root.querySelectorAll('.' + CLASS_SELECTED);
    Array.prototype.forEach.call(selected, (el) => {
      el.classList.remove(CLASS_SELECTED);
    });
    state.selection.forEach((p) => {
      elementsFor(p).forEach((el) => {
        el.classList.add(CLASS_SELECTED);
      });
    });
  }

  function fragmentOf(el) {
    const copy = el.cloneNode(true);
    const nodes = [copy].concat(
        Array.prototype.slice.call(copy.querySelectorAll('*')));
    nodes.forEach((n) => {
      n.classList.remove(CLASS_SELECTED, CLASS_HOVER);
      if (n.getAttribute('class') === '') n.removeAttribute('class');
    });
    return copy.outerHTML;
  }

  /**
   * 현재 선택을 "selected" 메시지 모양으로 설명한다.
   *
   * @return {{paths: !Array<string>, slots: !Array<?string>,
   *     rects: !Array<?Object>, htmlFragment: string}}
   */
  function selectionInfo() {
    const paths = state.selection.slice();
    const slots = [];
    const rects = [];
    const fragments = [];
    paths.forEach((p) => {
      const els = elementsFor(p);
      const el = els[0];
      slots.push(el ? el.getAttribute(ATTR_SLOT) || sourceOf(p) : sourceOf(p));
      if (el) {
        const r = el.getBoundingClientRect();
        rects.push({x: r.left, y: r.top, width: r.width, height: r.height});
        fragments.push(fragmentOf(el));
      } else {
        rects.push(null);
      }
    });
    return {
      paths: paths,
      slots: slots,
      rects: rects,
      htmlFragment: fragments.join('\n'),
    };
  }

  /**
   * 주어진 경로로 렌더된 요소를 하이라이트한다.
   *
   * @param {?Array<string>} paths 데이터 경로. 중복은 버린다.
   * @return {!Object} 선택 정보. selectionInfo() 참고.
   */
  function select(paths) {
    state.selection = (paths || []).filter((p, i, all) => {
      return all.indexOf(p) === i;
    });
    applySelectionClasses();
    return selectionInfo();
  }

  /**
   * 선택을 해제한다.
   *
   * @return {!Object} 선택 정보. selectionInfo() 참고.
   */
  function clearSelection() {
    return select([]);
  }

  // ---------------------------------------------------------------- 모드

  /**
   * 보기 모드와 편집 모드를 전환한다. 편집 모드를 벗어나면 선택과 hover를
   * 지운다.
   *
   * @param {string} mode "view" 또는 "edit".
   * @return {string} 현재 적용된 모드.
   */
  function setMode(mode) {
    if (mode !== 'view' && mode !== 'edit') {
      reportError(new Error('unknown mode "' + mode + '"'));
      return state.mode;
    }
    state.mode = mode;
    doc.documentElement.setAttribute('data-madang-mode', mode);
    if (mode === 'view') {
      clearSelection();
      setHover(null);
    }
    return mode;
  }

  function pathTarget(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el || !state.root || !state.root.contains(el)) return null;
    return el.closest('[' + ATTR_PATH + ']');
  }

  function setHover(el) {
    const path = el ? el.getAttribute(ATTR_PATH) : null;
    if (path === state.hoverPath) return;
    if (state.root) {
      const hovered = state.root.querySelectorAll('.' + CLASS_HOVER);
      Array.prototype.forEach.call(hovered, (n) => {
        n.classList.remove(CLASS_HOVER);
      });
    }
    state.hoverPath = path;
    if (path) {
      elementsFor(path).forEach((n) => {
        n.classList.add(CLASS_HOVER);
      });
    }
    post('hover', {path: path});
  }

  function onClick(e) {
    if (state.mode === 'edit') onEditClick(e);
    else onViewClick(e);
  }

  // 클릭은 선택, Ctrl/Cmd+클릭은 토글, 빈 곳 클릭은 해제한다.
  function onEditClick(e) {
    e.preventDefault();
    e.stopPropagation();
    const target = pathTarget(e.target);
    const additive = e.ctrlKey || e.metaKey;
    if (!target) {
      if (!additive && state.selection.length) {
        clearSelection();
        post('selected', selectionInfo());
      }
      return;
    }
    const path = target.getAttribute(ATTR_PATH);
    if (additive) toggleSelected(path);
    else state.selection = [path];
    applySelectionClasses();
    post('selected', selectionInfo());
  }

  function toggleSelected(path) {
    const at = state.selection.indexOf(path);
    if (at >= 0) state.selection.splice(at, 1);
    else state.selection.push(path);
  }

  // 링크는 따라가지 않고 호스트에 보고한다.
  function onViewClick(e) {
    const link = e.target && e.target.closest ?
      e.target.closest('a[href]') : null;
    if (!link) return;
    const href = link.getAttribute('href') || '';
    if (href.charAt(0) === '#') return;
    e.preventDefault();
    post('navigate', {url: link.href});
  }

  function onKeyDown(e) {
    if (e.key === 'Escape' && state.mode === 'edit' &&
        state.selection.length) {
      clearSelection();
      post('selected', selectionInfo());
    }
  }

  function onMouseOver(e) {
    if (state.mode !== 'edit') return;
    setHover(pathTarget(e.target));
  }

  function onMouseLeave() {
    if (state.mode === 'edit') setHover(null);
  }

  // ---------------------------------------------------------------- 브리지

  // 호스트 어댑터: window.madangBridge = { post(json) } (KCEF, Android, iOS).
  // 없으면 window.postMessage와 "madang" CustomEvent로 내보낸다.
  function post(type, payload) {
    const msg = {source: 'madang', type: type, payload: payload || {}};
    const bridge = state.bridge || global.madangBridge;
    try {
      if (bridge && typeof bridge.post === 'function') {
        bridge.post(JSON.stringify(msg));
        return;
      }
      global.postMessage(msg, '*');
      global.dispatchEvent(new global.CustomEvent('madang', {detail: msg}));
    } catch (err) {
      if (global.console) global.console.error('madang bridge failure', err);
    }
  }

  /**
   * 호스트로 메시지를 보내는 브리지를 바꾼다.
   *
   * @param {?{post: function(string)}} adapter 각 메시지를 JSON
   *     문자열로 받는다. null이면 window.madangBridge나 postMessage로 되돌아간다.
   */
  function setBridge(adapter) {
    state.bridge = adapter || null;
  }

  function reportError(err) {
    const message = err && err.message ? err.message : String(err);
    post('error', {message: message});
  }

  // ---------------------------------------------------------------- 마크다운

  /**
   * 마크다운 블록을 대상 요소에 그린다. setMarkdownRenderer()로 렌더러를
   * 붙이기 전에는 원문을 서식 없는 텍스트로 보여 준다.
   *
   * @param {string} source 마크다운 원문.
   * @param {{target: (?Element|undefined)}=} options 대상 요소. 기본은
   *     렌더 루트. 렌더러에도 전달한다.
   * @return {boolean} 렌더 성공 여부.
   */
  function renderMarkdown(source, options) {
    options = options || {};
    const target = options.target || rootElement();
    try {
      let out;
      if (state.markdownRenderer) {
        out = state.markdownRenderer(String(source || ''), options);
      } else {
        out = doc.createElement('pre');
        out.className = 'madang-md-plain';
        out.textContent = String(source || '');
      }
      while (target.firstChild) target.removeChild(target.firstChild);
      if (typeof out === 'string') target.innerHTML = out;
      else if (out) target.appendChild(out);
      return true;
    } catch (err) {
      reportError(err);
      return false;
    }
  }

  /**
   * 마크다운 렌더러를 붙인다.
   *
   * @param {?function(string, !Object): (?Node|string)} fn 노드 또는
   *     HTML 문자열을 돌려준다. 함수가 아닌 값을 주면 렌더러를 뗀다.
   */
  function setMarkdownRenderer(fn) {
    state.markdownRenderer = typeof fn === 'function' ? fn : null;
  }

  // ---------------------------------------------------------------- 스타일

  const CSS = [
    '.' + CLASS_SELECTED +
        '{outline:2px solid #3a5bd9 !important;outline-offset:2px;}',
    '.' + CLASS_HOVER + ':not(.' + CLASS_SELECTED + ')' +
        '{outline:1px dashed rgba(58,91,217,.7) !important;' +
        'outline-offset:2px;}',
    'html[data-madang-mode="edit"],html[data-madang-mode="edit"] *' +
        '{cursor:crosshair !important;}',
    'html[data-madang-mode="edit"] body::after' +
        '{content:"";position:fixed;inset:0;' +
        'border:2px solid rgba(58,91,217,.45);pointer-events:none;' +
        'z-index:2147483647;}',
  ].join('\n');

  function ensureStyle() {
    if (doc.getElementById('madang-runtime-style')) return;
    const el = doc.createElement('style');
    el.id = 'madang-runtime-style';
    el.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(el);
  }

  // ---------------------------------------------------------------- 시작

  function boot() {
    if (state.ready) return;
    state.ready = true;
    ensureStyle();
    doc.addEventListener('click', onClick, true);
    doc.addEventListener('keydown', onKeyDown, true);
    doc.addEventListener('mouseover', onMouseOver, true);
    doc.documentElement.addEventListener('mouseleave', onMouseLeave);
    global.addEventListener('error', (e) => {
      reportError(e.error || e.message);
    });
    doc.documentElement.setAttribute('data-madang-mode', state.mode);
    post('ready', {version: 1});
  }

  global.madang = {
    __runtime: true,
    version: 1,
    render: render,
    setMode: setMode,
    select: select,
    clearSelection: clearSelection,
    patchData: patchData,
    renderMarkdown: renderMarkdown,
    setMarkdownRenderer: setMarkdownRenderer,
    setBridge: setBridge,
    sourceOf: (path) => sourceOf(path),
    getData: () => clone(state.data),
    getMerged: () => clone(state.merged),
    getSelection: selectionInfo,
    getMode: () => state.mode,
  };

  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);
