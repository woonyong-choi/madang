/*
 * madang.js - template runtime for Madang views.
 *
 * Runs inside the WebView. Renders a template (page.html with data-bind
 * markers) from slot data, tracks which slot every rendered value came from,
 * handles element selection in edit mode and talks to the host app through
 * a pluggable bridge. No dependencies, no network access.
 */
(function (global) {
  'use strict';

  if (global.madang && global.madang.__runtime) return;

  var doc = global.document;
  var ATTR_PATH = 'data-madang-path';
  var ATTR_SLOT = 'data-madang-slot';
  var ATTR_TPL = 'data-madang-tpl';
  var TEMPLATE_SOURCE = 'template';
  var CLASS_SELECTED = 'madang-selected';
  var CLASS_HOVER = 'madang-hover';

  var state = {
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
    markdownRenderer: null
  };

  // ---------------------------------------------------------------- paths

  function parsePath(text) {
    var segs = [];
    var re = /([^.[\]]+)|\[(\d+)\]/g;
    var m;
    while ((m = re.exec(text)) !== null) {
      if (m[1] !== undefined) segs.push(m[1]);
      else segs.push(Number(m[2]));
    }
    return segs;
  }

  function formatPath(segs) {
    var out = '';
    for (var i = 0; i < segs.length; i++) {
      var s = segs[i];
      if (typeof s === 'number') out += '[' + s + ']';
      else out += (out ? '.' : '') + s;
    }
    return out;
  }

  function getAt(value, segs) {
    var cur = value;
    for (var i = 0; i < segs.length; i++) {
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
      var o = {};
      Object.keys(v).forEach(function (k) { o[k] = clone(v[k]); });
      return o;
    }
    return v;
  }

  // ---------------------------------------------------------------- merge

  function forgetSubtree(origin, prefix) {
    if (prefix === '') { origin.clear(); return; }
    origin.forEach(function (_, key) {
      if (key === prefix || key.indexOf(prefix + '.') === 0 || key.indexOf(prefix + '[') === 0) {
        origin.delete(key);
      }
    });
  }

  function recordSubtree(origin, value, segs, slot) {
    origin.set(formatPath(segs), slot);
    if (Array.isArray(value)) {
      value.forEach(function (item, i) { recordSubtree(origin, item, segs.concat(i), slot); });
    } else if (isPlainObject(value)) {
      Object.keys(value).forEach(function (k) { recordSubtree(origin, value[k], segs.concat(k), slot); });
    }
  }

  // Objects merge deeply, everything else (arrays included) is replaced whole.
  function combine(prev, next, slot, segs, origin) {
    if (next === undefined) return prev;
    if (isPlainObject(prev) && isPlainObject(next)) {
      var out = {};
      Object.keys(prev).forEach(function (k) { out[k] = prev[k]; });
      Object.keys(next).forEach(function (k) {
        out[k] = combine(prev[k], next[k], slot, segs.concat(k), origin);
      });
      origin.set(formatPath(segs), slot);
      return out;
    }
    forgetSubtree(origin, formatPath(segs));
    var copy = clone(next);
    recordSubtree(origin, copy, segs, slot);
    return copy;
  }

  function slotNames(template) {
    var slots = template && template.slots;
    if (!slots) return [];
    if (Array.isArray(slots)) {
      return slots.map(function (s) { return typeof s === 'string' ? s : s.name; });
    }
    return Object.keys(slots);
  }

  function recompute() {
    var order = state.slotOrder.slice();
    Object.keys(state.data).forEach(function (k) {
      if (order.indexOf(k) < 0) order.push(k);
    });
    var origin = new Map();
    var merged;
    order.forEach(function (slot) {
      if (state.data[slot] !== undefined) {
        merged = combine(merged, state.data[slot], slot, [], origin);
      }
    });
    state.merged = merged;
    state.origin = origin;
  }

  function sourceOf(path) {
    if (typeof path === 'string' && path.indexOf(TEMPLATE_SOURCE + ':') === 0) return TEMPLATE_SOURCE;
    var segs = typeof path === 'string' ? parsePath(path) : path;
    for (var n = segs.length; n >= 0; n--) {
      var key = formatPath(segs.slice(0, n));
      if (state.origin.has(key)) return state.origin.get(key);
    }
    return null;
  }

  // ---------------------------------------------------------------- render

  function rootElement() {
    return doc.querySelector('[data-madang-root]') || doc.body;
  }

  function takeSnapshot(root) {
    markTemplateText(root, []);
    var frag = doc.createDocumentFragment();
    Array.prototype.forEach.call(root.childNodes, function (n) { frag.appendChild(n.cloneNode(true)); });
    return frag;
  }

  function hasOwnText(el) {
    for (var n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3 && n.nodeValue.trim() !== '') return true;
    }
    return false;
  }

  // Tag elements holding fixed template text with a stable position key.
  function markTemplateText(el, chain) {
    Array.prototype.forEach.call(el.children, function (child, i) {
      var here = chain.concat(i);
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
    var segs = parsePath(expr);
    var slot = segs.shift();
    if (state.slotOrder.length && state.slotOrder.indexOf(slot) < 0 && !(slot in state.data)) {
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
    return v !== null && v !== undefined && v !== false && v !== '' && v !== 0;
  }

  // data-where="status=doing|todo" or "state!=superseded"
  function matchesWhere(item, where) {
    if (!where) return true;
    return where.split(';').every(function (clause) {
      var m = /^\s*([^!=\s]+)\s*(!?=)\s*(.*?)\s*$/.exec(clause);
      if (!m) return true;
      var actual = toText(getAt(item, parsePath(m[1])));
      var hit = m[3].split('|').map(function (s) { return s.trim(); }).indexOf(actual) >= 0;
      return m[2] === '=' ? hit : !hit;
    });
  }

  var UNSAFE_URL = /^\s*(javascript|vbscript|data:text\/html)/i;

  function setPath(el, segs) {
    var path = formatPath(segs);
    el.setAttribute(ATTR_PATH, path);
    el.setAttribute(ATTR_SLOT, sourceOf(segs) || '');
  }

  function processElement(el, scope) {
    if (el.hasAttribute('data-each')) { expandEach(el, scope); return; }
    if (el.hasAttribute('data-if')) {
      var cond = getAt(state.merged, resolve(el.getAttribute('data-if'), scope));
      if (!truthy(cond)) { el.remove(); return; }
    }
    if (el.hasAttribute('data-unless')) {
      var neg = getAt(state.merged, resolve(el.getAttribute('data-unless'), scope));
      if (truthy(neg)) { el.remove(); return; }
    }

    var attrPath = null;
    Array.prototype.slice.call(el.attributes).forEach(function (a) {
      if (a.name.indexOf('data-attr-') !== 0) return;
      var name = a.name.slice('data-attr-'.length);
      if (/^on/i.test(name)) return;
      var segs = resolve(a.value, scope);
      var v = getAt(state.merged, segs);
      if (v === null || v === undefined || v === false) { el.removeAttribute(name); return; }
      var s = toText(v);
      if ((name === 'href' || name === 'src' || name === 'action' || name === 'formaction' || name === 'poster' || name === 'xlink:href') && UNSAFE_URL.test(s)) {
        el.removeAttribute(name);
        return;
      }
      el.setAttribute(name, s);
      if (!attrPath) attrPath = segs;
    });

    if (el.hasAttribute('data-bind')) {
      var bsegs = resolve(el.getAttribute('data-bind'), scope);
      el.textContent = toText(getAt(state.merged, bsegs));
      setPath(el, bsegs);
      el.removeAttribute(ATTR_TPL);
      return;
    }
    if (attrPath && !el.hasAttribute(ATTR_PATH)) setPath(el, attrPath);

    if (el.hasAttribute(ATTR_TPL)) {
      if (!el.hasAttribute(ATTR_PATH)) {
        var key = TEMPLATE_SOURCE + ':' + el.getAttribute(ATTR_TPL) + (scope.length ? '@' + formatPath(scope) : '');
        el.setAttribute(ATTR_PATH, key);
        el.setAttribute(ATTR_SLOT, TEMPLATE_SOURCE);
      }
      el.removeAttribute(ATTR_TPL);
    }

    Array.prototype.slice.call(el.children).forEach(function (child) { processElement(child, scope); });
  }

  function expandEach(el, scope) {
    var segs = resolve(el.getAttribute('data-each'), scope);
    var list = getAt(state.merged, segs);
    var where = el.getAttribute('data-where');
    var parent = el.parentNode;
    if (Array.isArray(list)) {
      list.forEach(function (item, i) {
        if (!matchesWhere(item, where)) return;
        var itemSegs = segs.concat(i);
        var copy = el.cloneNode(true);
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
    var style = doc.documentElement.style;
    state.themeVars.forEach(function (name) { style.removeProperty(name); });
    state.themeVars = [];
    var flat = {};
    (function walk(obj, prefix) {
      Object.keys(obj || {}).forEach(function (k) {
        var key = prefix ? prefix + '.' + k : k;
        if (isPlainObject(obj[k])) walk(obj[k], key);
        else flat[key] = obj[k];
      });
    })(theme, '');
    Object.keys(flat).forEach(function (key) {
      var v = flat[key];
      if (typeof v === 'number' && /size|width|gap|radius/.test(key)) v = v + 'px';
      var name = '--' + key.replace(/[^a-zA-Z0-9]+/g, '-');
      style.setProperty(name, String(v));
      state.themeVars.push(name);
    });
  }

  function paint() {
    var root = state.root;
    while (root.firstChild) root.removeChild(root.firstChild);
    root.appendChild(state.snapshot.cloneNode(true));
    Array.prototype.slice.call(root.children).forEach(function (child) { processElement(child, []); });
    applySelectionClasses();
  }

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
      state.selection = state.selection.filter(function (p) { return elementsFor(p).length > 0; });
      applySelectionClasses();
      setMode(mode || state.mode);
      return true;
    } catch (err) {
      reportError(err);
      return false;
    }
  }

  // ---------------------------------------------------------------- data edit

  function setAt(obj, segs, value) {
    var cur = obj;
    for (var i = 0; i < segs.length - 1; i++) {
      var s = segs[i];
      if (cur[s] === null || typeof cur[s] !== 'object') {
        cur[s] = typeof segs[i + 1] === 'number' ? [] : {};
      }
      cur = cur[s];
    }
    cur[segs[segs.length - 1]] = value;
  }

  function patchData(path, value, slot) {
    try {
      if (typeof path === 'string' && path.indexOf(TEMPLATE_SOURCE + ':') === 0) {
        throw new Error('fixed template text cannot be patched as data: "' + path + '"');
      }
      var segs = parsePath(path);
      if (!segs.length) throw new Error('empty path');
      var target = slot || sourceOf(segs);
      if (!target) {
        target = state.slotOrder.filter(function (s) { return state.data[s] !== undefined; })[0] || state.slotOrder[0];
      }
      if (!target) throw new Error('no slot to patch');
      if (!isPlainObject(state.data[target])) state.data[target] = {};
      setAt(state.data[target], segs, clone(value));
      recompute();
      paint();
      return { slot: target, path: formatPath(segs) };
    } catch (err) {
      reportError(err);
      return null;
    }
  }

  // ---------------------------------------------------------------- selection

  function elementsFor(path) {
    if (!state.root) return [];
    return Array.prototype.filter.call(state.root.querySelectorAll('[' + ATTR_PATH + ']'), function (el) {
      return el.getAttribute(ATTR_PATH) === path;
    });
  }

  function applySelectionClasses() {
    if (!state.root) return;
    Array.prototype.forEach.call(state.root.querySelectorAll('.' + CLASS_SELECTED), function (el) {
      el.classList.remove(CLASS_SELECTED);
    });
    state.selection.forEach(function (p) {
      elementsFor(p).forEach(function (el) { el.classList.add(CLASS_SELECTED); });
    });
  }

  function fragmentOf(el) {
    var copy = el.cloneNode(true);
    [copy].concat(Array.prototype.slice.call(copy.querySelectorAll('*'))).forEach(function (n) {
      n.classList.remove(CLASS_SELECTED, CLASS_HOVER);
      if (n.getAttribute('class') === '') n.removeAttribute('class');
    });
    return copy.outerHTML;
  }

  function selectionInfo() {
    var paths = state.selection.slice();
    var slots = [];
    var rects = [];
    var fragments = [];
    paths.forEach(function (p) {
      var els = elementsFor(p);
      var el = els[0];
      slots.push(el ? el.getAttribute(ATTR_SLOT) || sourceOf(p) : sourceOf(p));
      if (el) {
        var r = el.getBoundingClientRect();
        rects.push({ x: r.left, y: r.top, width: r.width, height: r.height });
        fragments.push(fragmentOf(el));
      } else {
        rects.push(null);
      }
    });
    return { paths: paths, slots: slots, rects: rects, htmlFragment: fragments.join('\n') };
  }

  function select(paths) {
    state.selection = (paths || []).filter(function (p, i, all) { return all.indexOf(p) === i; });
    applySelectionClasses();
    return selectionInfo();
  }

  function clearSelection() {
    return select([]);
  }

  // ---------------------------------------------------------------- mode

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
    var el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el || !state.root || !state.root.contains(el)) return null;
    return el.closest('[' + ATTR_PATH + ']');
  }

  function setHover(el) {
    var path = el ? el.getAttribute(ATTR_PATH) : null;
    if (path === state.hoverPath) return;
    if (state.root) {
      Array.prototype.forEach.call(state.root.querySelectorAll('.' + CLASS_HOVER), function (n) {
        n.classList.remove(CLASS_HOVER);
      });
    }
    state.hoverPath = path;
    if (path) {
      elementsFor(path).forEach(function (n) { n.classList.add(CLASS_HOVER); });
    }
    post('hover', { path: path });
  }

  function onClick(e) {
    if (state.mode === 'edit') {
      e.preventDefault();
      e.stopPropagation();
      var target = pathTarget(e.target);
      var additive = e.ctrlKey || e.metaKey;
      if (!target) {
        if (!additive && state.selection.length) {
          clearSelection();
          post('selected', selectionInfo());
        }
        return;
      }
      var path = target.getAttribute(ATTR_PATH);
      if (additive) {
        var at = state.selection.indexOf(path);
        if (at >= 0) state.selection.splice(at, 1);
        else state.selection.push(path);
      } else {
        state.selection = [path];
      }
      applySelectionClasses();
      post('selected', selectionInfo());
      return;
    }
    var link = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!link) return;
    var href = link.getAttribute('href') || '';
    if (href.charAt(0) === '#') return;
    e.preventDefault();
    post('navigate', { url: link.href });
  }

  function onKeyDown(e) {
    if (e.key === 'Escape' && state.mode === 'edit' && state.selection.length) {
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

  // ---------------------------------------------------------------- bridge

  // Host adapters: window.madangBridge = { post(json) } (KCEF, Android, iOS).
  // Without one, messages go out via window.postMessage and a "madang" CustomEvent.
  function post(type, payload) {
    var msg = { source: 'madang', type: type, payload: payload || {} };
    var bridge = state.bridge || global.madangBridge;
    try {
      if (bridge && typeof bridge.post === 'function') {
        bridge.post(JSON.stringify(msg));
        return;
      }
      global.postMessage(msg, '*');
      global.dispatchEvent(new global.CustomEvent('madang', { detail: msg }));
    } catch (err) {
      if (global.console) global.console.error('madang bridge failure', err);
    }
  }

  function setBridge(adapter) {
    state.bridge = adapter || null;
  }

  function reportError(err) {
    var message = err && err.message ? err.message : String(err);
    post('error', { message: message });
  }

  // ---------------------------------------------------------------- markdown

  // Entry point for markdown blocks. A renderer is plugged in with
  // setMarkdownRenderer(fn(source, options) -> Node | html string); until then
  // the source is shown as plain preformatted text.
  function renderMarkdown(source, options) {
    options = options || {};
    var target = options.target || rootElement();
    try {
      var out;
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

  function setMarkdownRenderer(fn) {
    state.markdownRenderer = typeof fn === 'function' ? fn : null;
  }

  // ---------------------------------------------------------------- style

  var CSS = [
    '.' + CLASS_SELECTED + '{outline:2px solid #3a5bd9 !important;outline-offset:2px;}',
    '.' + CLASS_HOVER + ':not(.' + CLASS_SELECTED + '){outline:1px dashed rgba(58,91,217,.7) !important;outline-offset:2px;}',
    'html[data-madang-mode="edit"],html[data-madang-mode="edit"] *{cursor:crosshair !important;}',
    'html[data-madang-mode="edit"] body::after{content:"";position:fixed;inset:0;border:2px solid rgba(58,91,217,.45);pointer-events:none;z-index:2147483647;}'
  ].join('\n');

  function ensureStyle() {
    if (doc.getElementById('madang-runtime-style')) return;
    var el = doc.createElement('style');
    el.id = 'madang-runtime-style';
    el.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(el);
  }

  // ---------------------------------------------------------------- boot

  function boot() {
    if (state.ready) return;
    state.ready = true;
    ensureStyle();
    doc.addEventListener('click', onClick, true);
    doc.addEventListener('keydown', onKeyDown, true);
    doc.addEventListener('mouseover', onMouseOver, true);
    doc.documentElement.addEventListener('mouseleave', onMouseLeave);
    global.addEventListener('error', function (e) { reportError(e.error || e.message); });
    doc.documentElement.setAttribute('data-madang-mode', state.mode);
    post('ready', { version: 1 });
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
    sourceOf: function (path) { return sourceOf(path); },
    getData: function () { return clone(state.data); },
    getMerged: function () { return clone(state.merged); },
    getSelection: selectionInfo,
    getMode: function () { return state.mode; }
  };

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot);
  else boot();
})(window);
