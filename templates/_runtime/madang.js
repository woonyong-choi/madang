/*
 * madang.js - template runtime for Madang views.
 *
 * Runs inside the WebView. Renders a template (page.html with data-bind
 * markers) from slot data, tracks which slot every rendered value came from,
 * handles element selection in edit mode and talks to the host app through
 * a pluggable bridge. No dependencies, no network access.
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

  // ---------------------------------------------------------------- paths

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

  // ---------------------------------------------------------------- merge

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

  // Objects merge deeply, everything else (arrays included) is replaced whole.
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

  // Paths of fixed template text look like "template:<position>".
  function isTemplatePath(path) {
    return typeof path === 'string' &&
        path.indexOf(TEMPLATE_SOURCE + ':') === 0;
  }

  /**
   * Returns the slot that supplied the value at a path. The nearest recorded
   * ancestor wins; fixed template text belongs to the "template" source.
   *
   * @param {string|!Array<string|number>} path Data path or its segments.
   * @return {?string} Slot name, "template", or null when nothing matches.
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

  // ---------------------------------------------------------------- render

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

  // Tag elements holding fixed template text with a stable position key.
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

  // data-if keeps the element when the value is truthy, data-unless when not.
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

  // Fills data-attr-<name> attributes; returns the first bound path.
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

  // Gives fixed template text a "template:<position>[@scope]" path.
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

  // {color: {accent: x}} becomes {'color.accent': x}.
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

  // Bare numbers for sizes get a px unit.
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
   * Renders a template with slot data and a theme. Failures are reported to
   * the host as an "error" message instead of being thrown.
   *
   * @param {?Object} template `{name, version, slots, html?}`. `slots` is an
   *     array of names, an array of `{name}`, or an ordered object. When
   *     `html` is given it replaces the current markup.
   * @param {?Object} data Slot name to JSON value.
   * @param {?Object} theme Nested style variables, e.g. `{color: {accent}}`.
   * @param {string=} mode "view" or "edit"; keeps the current mode if absent.
   * @return {boolean} Whether rendering succeeded.
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

  // ---------------------------------------------------------------- data edit

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
   * Replaces one value and repaints at once.
   *
   * @param {string} path Data path such as `work[1].company`.
   * @param {*} value New value; it is copied.
   * @param {string=} slot Slot to write to. Defaults to the slot that
   *     supplied the current value, then the first slot with data.
   * @return {?{slot: string, path: string}} Where the value was written, or
   *     null on failure.
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

  // ---------------------------------------------------------------- selection

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
   * Describes the current selection in the shape of the "selected" message.
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
   * Highlights the elements rendered for the given paths.
   *
   * @param {?Array<string>} paths Data paths; duplicates are dropped.
   * @return {!Object} Selection info, see selectionInfo().
   */
  function select(paths) {
    state.selection = (paths || []).filter((p, i, all) => {
      return all.indexOf(p) === i;
    });
    applySelectionClasses();
    return selectionInfo();
  }

  /**
   * Clears the selection.
   *
   * @return {!Object} Selection info, see selectionInfo().
   */
  function clearSelection() {
    return select([]);
  }

  // ---------------------------------------------------------------- mode

  /**
   * Switches between view and edit mode. Leaving edit mode clears the
   * selection and hover.
   *
   * @param {string} mode "view" or "edit".
   * @return {string} The mode now in effect.
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

  // Click selects, Ctrl/Cmd+click toggles, a click on nothing clears.
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

  // Links are reported to the host instead of being followed.
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

  // ---------------------------------------------------------------- bridge

  // Host adapters: window.madangBridge = { post(json) } (KCEF, Android, iOS).
  // Without one, messages go out via window.postMessage and a "madang"
  // CustomEvent.
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
   * Replaces the bridge used to send messages to the host.
   *
   * @param {?{post: function(string)}} adapter Receives each message as a
   *     JSON string; null falls back to window.madangBridge or postMessage.
   */
  function setBridge(adapter) {
    state.bridge = adapter || null;
  }

  function reportError(err) {
    const message = err && err.message ? err.message : String(err);
    post('error', {message: message});
  }

  // ---------------------------------------------------------------- markdown

  /**
   * Renders a markdown block into a target element. Until a renderer is set
   * with setMarkdownRenderer() the source is shown as preformatted text.
   *
   * @param {string} source Markdown source.
   * @param {{target: (?Element|undefined)}=} options Target element; the
   *     render root by default. Also passed to the renderer.
   * @return {boolean} Whether rendering succeeded.
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
   * Plugs in a markdown renderer.
   *
   * @param {?function(string, !Object): (?Node|string)} fn Returns a node or
   *     an HTML string; anything other than a function removes the renderer.
   */
  function setMarkdownRenderer(fn) {
    state.markdownRenderer = typeof fn === 'function' ? fn : null;
  }

  // ---------------------------------------------------------------- style

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

  // ---------------------------------------------------------------- boot

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
