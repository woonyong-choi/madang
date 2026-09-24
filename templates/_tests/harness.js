const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');

const TEMPLATES = path.resolve(__dirname, '..');
const RUNTIME = path.join(TEMPLATES, '_runtime', 'madang.js');
const NAMES = ['table', 'decisions', 'tasks', 'resume'];

/**
 * @param {string} file Path to a JSON file.
 * @return {*} Parsed content.
 */
function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

/**
 * @param {string} name Template name.
 * @return {!Object} The template's entry in index.json.
 */
function templateEntry(name) {
  const index = readJson(path.join(TEMPLATES, 'index.json'));
  const entry = index.templates.find((t) => t.name === name);
  if (!entry) throw new Error(`template ${name} missing from index.json`);
  return entry;
}

/**
 * @param {string} name Template name.
 * @return {!Object} The template's sample.json.
 */
function sample(name) {
  return readJson(path.join(TEMPLATES, name, 'sample.json'));
}

/**
 * @param {string} name Template name.
 * @return {!Object} The template's theme.json.
 */
function theme(name) {
  return readJson(path.join(TEMPLATES, name, 'theme.json'));
}

/**
 * Injects the runtime the way a host WebView does (outside the page's CSP),
 * records every bridge message and every non-local request that was sent.
 *
 * @param {!Object} page Playwright page.
 * @param {string} name Template name.
 * @param {{data: ?, theme: ?, mode: (string|undefined)}=} opts Overrides for
 *     the sample data, theme and mode.
 * @return {!Promise<{external: !Array<string>}>} Non-local request URLs.
 */
async function openTemplate(page, name, opts = {}) {
  const external = [];
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith('file:') && !url.startsWith('data:')) {
      external.push(url);
    }
  });
  // Chromium reports CSP-blocked loads as requests that fail with "csp";
  // those never reach the network, so they are not counted.
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
 * @param {!Object} page Playwright page opened with openTemplate().
 * @param {string=} type Message type to keep; all messages when absent.
 * @return {!Promise<!Array<!Object>>} Bridge messages posted so far.
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
