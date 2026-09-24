const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const TEMPLATES = path.resolve(__dirname, '..');
const RUNTIME = path.join(TEMPLATES, '_runtime', 'madang.js');
const NAMES = ['table', 'decisions', 'tasks', 'resume'];

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function templateEntry(name) {
  const index = readJson(path.join(TEMPLATES, 'index.json'));
  const entry = index.templates.find((t) => t.name === name);
  if (!entry) throw new Error(`template ${name} missing from index.json`);
  return entry;
}

function sample(name) {
  return readJson(path.join(TEMPLATES, name, 'sample.json'));
}

function theme(name) {
  return readJson(path.join(TEMPLATES, name, 'theme.json'));
}

// Injects the runtime the way a host WebView does (outside the page's CSP),
// records every bridge message and every non-local request that was sent.
async function openTemplate(page, name, opts = {}) {
  const external = [];
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith('file:') && !url.startsWith('data:')) external.push(url);
  });
  // Chromium reports CSP-blocked loads as requests that fail with "csp";
  // those never reach the network, so they are not counted.
  page.on('requestfailed', (req) => {
    const at = external.indexOf(req.url());
    if (at >= 0 && req.failure() && req.failure().errorText === 'csp') external.splice(at, 1);
  });
  await page.addInitScript(() => {
    window.__madangEvents = [];
    window.addEventListener('madang', (e) => window.__madangEvents.push(e.detail));
    document.addEventListener('securitypolicyviolation', (e) => {
      (window.__cspViolations = window.__cspViolations || []).push(e.blockedURI);
    });
  });
  await page.addInitScript({ path: RUNTIME });
  await page.goto(pathToFileURL(path.join(TEMPLATES, name, 'page.html')).href);
  const ok = await page.evaluate(
    ([tpl, data, th, mode]) => window.madang.render(tpl, data, th, mode),
    [templateEntry(name), opts.data || sample(name), opts.theme || theme(name), opts.mode || 'view']
  );
  if (!ok) {
    const events = await events_(page);
    throw new Error('render failed: ' + JSON.stringify(events.filter((e) => e.type === 'error')));
  }
  return { external };
}

async function events_(page, type) {
  const all = await page.evaluate(() => window.__madangEvents.slice());
  return type ? all.filter((e) => e.type === type) : all;
}

module.exports = { TEMPLATES, RUNTIME, NAMES, readJson, templateEntry, sample, theme, openTemplate, events: events_ };
