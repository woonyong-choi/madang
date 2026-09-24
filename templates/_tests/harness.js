const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');

const TEMPLATES = path.resolve(__dirname, '..');
const RUNTIME = path.join(TEMPLATES, '_runtime', 'madang.js');
const NAMES = ['table', 'decisions', 'tasks', 'resume'];

/**
 * @param {string} file JSON 파일 경로.
 * @return {*} 파싱한 내용.
 */
function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

/**
 * @param {string} name 템플릿 이름.
 * @return {!Object} index.json의 해당 템플릿 항목.
 */
function templateEntry(name) {
  const index = readJson(path.join(TEMPLATES, 'index.json'));
  const entry = index.templates.find((t) => t.name === name);
  if (!entry) throw new Error(`template ${name} missing from index.json`);
  return entry;
}

/**
 * @param {string} name 템플릿 이름.
 * @return {!Object} 해당 템플릿의 sample.json.
 */
function sample(name) {
  return readJson(path.join(TEMPLATES, name, 'sample.json'));
}

/**
 * @param {string} name 템플릿 이름.
 * @return {!Object} 해당 템플릿의 theme.json.
 */
function theme(name) {
  return readJson(path.join(TEMPLATES, name, 'theme.json'));
}

/**
 * 호스트 WebView가 하듯 런타임을 주입하고(페이지 CSP 바깥), 브리지 메시지와
 * 로컬이 아닌 요청을 모두 기록한다.
 *
 * @param {!Object} page Playwright 페이지.
 * @param {string} name 템플릿 이름.
 * @param {{data: ?, theme: ?, mode: (string|undefined)}=} opts 샘플 데이터,
 *     테마, 모드를 덮어쓰는 값.
 * @return {!Promise<{external: !Array<string>}>} 로컬이 아닌 요청 URL.
 */
async function openTemplate(page, name, opts = {}) {
  const external = [];
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith('file:') && !url.startsWith('data:')) {
      external.push(url);
    }
  });
  // Chromium은 CSP로 막힌 로드를 "csp"로 실패한 요청으로 보고한다.
  // 이런 요청은 네트워크에 나가지 않으므로 세지 않는다.
  page.on('requestfailed', (req) => {
    const at = external.indexOf(req.url());
    if (at >= 0 && req.failure() && req.failure().errorText === 'csp') {
      external.splice(at, 1);
    }
  });
  await page.addInitScript(() => {
    window.__madangEvents = [];
    window.addEventListener('madang', (e) => {
      window.__madangEvents.push(e.detail);
    });
    document.addEventListener('securitypolicyviolation', (e) => {
      window.__cspViolations = window.__cspViolations || [];
      window.__cspViolations.push(e.blockedURI);
    });
  });
  await page.addInitScript({path: RUNTIME});
  const pageUrl = pathToFileURL(path.join(TEMPLATES, name, 'page.html'));
  await page.goto(pageUrl.href);
  const ok = await page.evaluate(
      ([tpl, data, th, mode]) => window.madang.render(tpl, data, th, mode),
      [
        templateEntry(name),
        opts.data || sample(name),
        opts.theme || theme(name),
        opts.mode || 'view',
      ],
  );
  if (!ok) {
    const errors = await events_(page, 'error');
    throw new Error('render failed: ' + JSON.stringify(errors));
  }
  return {external};
}

/**
 * @param {!Object} page openTemplate()으로 연 Playwright 페이지.
 * @param {string=} type 남길 메시지 종류. 없으면 모든 메시지.
 * @return {!Promise<!Array<!Object>>} 지금까지 보낸 브리지 메시지.
 */
async function events_(page, type) {
  const all = await page.evaluate(() => window.__madangEvents.slice());
  return type ? all.filter((e) => e.type === type) : all;
}

module.exports = {
  TEMPLATES,
  RUNTIME,
  NAMES,
  readJson,
  templateEntry,
  sample,
  theme,
  openTemplate,
  events: events_,
};
