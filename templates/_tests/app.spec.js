const fs = require('fs');
const os = require('os');
const path = require('path');
const {pathToFileURL} = require('url');
const {test, expect} = require('@playwright/test');
const {TEMPLATES, readJson, trackExternal} = require('./harness');
const renderer = require('../_runtime/document.js');

const APP_HOST = path.join(TEMPLATES, '_runtime', 'app.html');
const SHELL = path.join(
    TEMPLATES, '..', 'core', 'madang', 'publish', 'shell.html');
const RESUME = path.join(TEMPLATES, 'viewers', 'resume-basic');
const RESUME_HTML = fs.readFileSync(path.join(RESUME, 'index.html'), 'utf8');
const RESUME_SAMPLE = readJson(path.join(RESUME, 'sample.json'));
const RESUME_KEY = 'resume/basic data=./base.json';

// core가 쓰는 page.md 모양: 개요 뒤에 블록 머리 주석과 본문이 쌓인다.
const PAGE = [
  '---',
  'title: 이력서',
  '---',
  '이력서를 다듬는 페이지.',
  '',
  '<!-- b01 | 2026-09-24T08:11:02+09:00 | user | target=page -->',
  '이력서 템플릿 만들어줘',
  '',
  '<!-- b02 | 2026-09-24T08:11:03+09:00 | router | run=1 -->',
  'kind=design → claude/claude-opus-5-5',
  '',
  '<!-- b03 | 2026-09-24T08:14:40+09:00 | agent | run=1 -->',
  '뷰를 **만들었습니다**.',
  '',
  '```view ' + RESUME_KEY,
  '```',
  '',
  '<!-- b04 |  | doc | file=blocks/b04-cover.md title=%EC%BB%A4%EB%B2%84 -->',
  '---',
  'kind: cover',
  '---',
  '## 커버레터',
  '',
  '<!-- b05 | 2026-09-24T09:00:00+09:00 | router | run=2 ask=true ' +
      'options=merge,keep -->',
  '테스트가 실패했습니다. 어떻게 할까요?',
  '',
  '<!-- b06 | 2026-09-24T09:01:00+09:00 | user | answer=b05 -->',
  'keep',
  '',
  '<!-- 그냥 주석 -->',
  '',
].join('\n');

const RUNS = [
  {n: 1, after: 'b01', title: 'claude/opus', summary: '입력 12k',
    files: ['a.md']},
  {n: 2, status: 'failed'},
];

/**
 * 앱 문서 탭 호스트를 열고 문서를 그린다. 앱에 보내는 요청은 모아 둔다.
 *
 * @param {!Object} page Playwright 페이지.
 * @param {!Object} payload madangApp.render()에 넘길 값.
 * @return {!Promise<!Array<string>>} 로컬이 아닌 요청 URL.
 */
async function openApp(page, payload) {
  const external = trackExternal(page);
  await page.goto(pathToFileURL(APP_HOST).href);
  await page.evaluate((p) => {
    window.sent = [];
    window.madangApp.post = (request) => window.sent.push(request);
    window.madangApp.render(p);
  }, payload);
  return external;
}

test.describe('page blocks', () => {
  test('block head comments become block components', async ({page}) => {
    await openApp(page, {markdown: PAGE, context: {runs: RUNS}});
    const doc = page.locator('#madang-page .madang-document');
    await expect(doc.locator('> p').first()).toHaveText('이력서를 다듬는 페이지.');
    const blocks = doc.locator('.madang-block');
    await expect(blocks).toHaveCount(8);
    const kinds = await blocks.evaluateAll((els) => {
      return els.map((el) => el.getAttribute('data-kind'));
    });
    expect(kinds).toEqual([
      'request', 'run', 'route', 'result', 'doc', 'ask', 'answer', 'run',
    ]);
    await expect(doc.locator('.madang-block-label')).toHaveText([
      '요청', '실행 1', '라우팅', '결과', '문서', '묻는 블록', '답', '실행 2',
    ]);
    await expect(doc.locator('details.madang-block')).toHaveCount(3);
    await expect(doc.locator('[data-block="b01"] time')).toHaveText('08:11');
    await expect(doc.locator('[data-block="b03"] .madang-block-body strong'))
        .toHaveText('만들었습니다');
    await expect(doc.locator('[data-block="b04"] .madang-block-title'))
        .toHaveText('커버');
    await expect(doc.locator('[data-block="b04"] details.madang-frontmatter'))
        .toHaveCount(1);
    await expect(doc.locator('[data-block="b04"] h2')).toHaveText('커버레터');
    await expect(doc.locator('[data-run="1"][data-kind="run"] li code'))
        .toHaveText('a.md');
    await expect(doc).toContainText('<!-- 그냥 주석 -->');
  });

  test('blocks keep view fences and node renders the same', async ({page}) => {
    const context = {
      views: {[RESUME_KEY]: {status: 'ok', html: RESUME_HTML,
        data: RESUME_SAMPLE}},
      runs: RUNS,
    };
    await openApp(page, {markdown: PAGE, context: context});
    const frame = page.locator('[data-block="b03"] iframe.madang-view-frame');
    await expect(frame).toHaveCount(1);
    const html = await page.evaluate(() => {
      return document.getElementById('madang-page').innerHTML;
    });
    const direct = renderer.renderDocument(PAGE, context).html;
    const normalized = await page.evaluate((h) => {
      const div = document.createElement('div');
      div.innerHTML = h;
      div.querySelectorAll('iframe').forEach((f) => f.removeAttribute('style'));
      return div.innerHTML;
    }, direct);
    const shown = await page.evaluate((h) => {
      const div = document.createElement('div');
      div.innerHTML = h;
      div.querySelectorAll('iframe').forEach((f) => f.removeAttribute('style'));
      return div.innerHTML;
    }, html);
    expect(shown).toBe(normalized);
  });
});

test.describe('app host', () => {
  test('view renders under the host policy with app tokens', async ({page}) => {
    const tokens = {bg: '#101418', text: '#e6e9ef', accent: '#8ab4ff',
      font: 'serif', radius: '10px'};
    const markdown = '# 이력서\n\n```view ' + RESUME_KEY + '\n```\n';
    const context = {
      views: {[RESUME_KEY]: {status: 'ok', html: RESUME_HTML,
        data: RESUME_SAMPLE}},
      tokens: tokens,
    };
    const payload = {markdown: markdown, context: context};
    const external = await openApp(page, payload);
    await expect(page.locator('html')).toHaveCSS(
        'background-color', 'rgb(16, 20, 24)');
    await expect(page.locator('h1').first()).toHaveCSS(
        'color', 'rgb(230, 233, 239)');
    const frame = page.locator('iframe.madang-view-frame');
    await expect(frame).toHaveAttribute('sandbox', 'allow-scripts');
    const view = page.frameLocator('iframe.madang-view-frame');
    await expect(view.locator('h1')).toHaveText(RESUME_SAMPLE.name);
    const accent = await page.frames()[1].evaluate(() => {
      return getComputedStyle(document.documentElement)
          .getPropertyValue('--app-accent').trim();
    });
    expect(accent).toBe('#8ab4ff');
    await page.waitForTimeout(200);
    expect(external).toEqual([]);
  });

  test('links become app requests', async ({page}) => {
    const markdown = PAGE + '\n[표](./table.csv) [밖](https://example.com/) ' +
        '[위로](#top)\n';
    const context = {views: {[RESUME_KEY]: {status: 'missing'}}, runs: RUNS};
    await openApp(page, {markdown: markdown, context: context});
    await page.locator('a.madang-view-data').click();
    await page.locator('[data-block="b04"] a.madang-block-open').click();
    await page.locator('[data-kind="run"][data-run="1"] a.madang-block-open')
        .click();
    await page.getByText('표', {exact: true}).click();
    await page.getByText('밖', {exact: true}).click();
    await page.getByText('위로', {exact: true}).click();
    const sent = await page.evaluate(() => window.sent);
    expect(sent).toEqual([
      {type: 'open', href: './base.json'},
      {type: 'block', id: 'b04', href: 'blocks/b04-cover.md'},
      {type: 'run', n: '1'},
      {type: 'open', href: './table.csv'},
      {type: 'open', href: 'https://example.com/'},
    ]);
    await expect(page.locator('details[data-kind="run"][data-run="1"]'))
        .not.toHaveAttribute('open', '');
  });

  test('double click opens a block', async ({page}) => {
    await openApp(page, {markdown: PAGE, context: {runs: RUNS}});
    await page.locator('[data-block="b04"] h2').dblclick();
    await page.locator('[data-block="b01"]').dblclick();
    const sent = await page.evaluate(() => window.sent);
    expect(sent).toEqual([
      {type: 'block', id: 'b04', href: 'blocks/b04-cover.md'},
    ]);
  });

  test('re-render keeps scroll and follows new blocks', async ({page}) => {
    const filler = Array.from({length: 60}, (_, i) => `줄 ${i}\n`).join('\n');
    const first = filler + '<!-- b01 | | user -->\n요청\n';
    await openApp(page, {markdown: first, follow: true});
    expect(await page.evaluate(() => scrollY)).toBe(0);
    await page.evaluate((md) => {
      window.madangApp.render({markdown: md, follow: true});
    }, first);
    expect(await page.evaluate(() => scrollY)).toBe(0);
    const second = first + '<!-- b02 | | agent | run=1 -->\n결과\n';
    await page.evaluate((md) => {
      window.madangApp.render({markdown: md, follow: true});
    }, second);
    const atEnd = await page.evaluate(() => {
      const el = document.scrollingElement;
      return el.scrollHeight - el.scrollTop - el.clientHeight < 2;
    });
    expect(atEnd).toBe(true);
  });
});

test.describe('view data link', () => {
  test('only fences with data get a data link', () => {
    const markdown = '```view ' + RESUME_KEY + '\n```\n\n' +
        '```view demo/none\n```\n\n```view demo/bad data=javascript:x\n```\n';
    const html = renderer.renderDocument(markdown, {}).html;
    expect(html.match(/madang-view-data/g)).toHaveLength(1);
    expect(html).toContain('href="./base.json" data-open="data"');
  });
});

/**
 * 두 PNG에서 다른 픽셀의 비율을 브라우저 캔버스로 센다.
 *
 * @param {!Object} page Playwright 페이지.
 * @param {!Buffer} a 첫 스크린샷.
 * @param {!Buffer} b 둘째 스크린샷.
 * @return {!Promise<number>} 다른 픽셀 비율. 크기가 다르면 1.
 */
async function differingRatio(page, a, b) {
  return page.evaluate(async ([left, right]) => {
    const load = async (base64) => {
      const img = new Image();
      img.src = 'data:image/png;base64,' + base64;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      const context = canvas.getContext('2d');
      context.drawImage(img, 0, 0);
      return context.getImageData(0, 0, img.width, img.height);
    };
    const [x, y] = [await load(left), await load(right)];
    if (x.width !== y.width || x.height !== y.height) return 1;
    let differing = 0;
    for (let i = 0; i < x.data.length; i += 4) {
      if (x.data[i] !== y.data[i] || x.data[i + 1] !== y.data[i + 1] ||
          x.data[i + 2] !== y.data[i + 2]) differing++;
    }
    return differing / (x.width * x.height);
  }, [a.toString('base64'), b.toString('base64')]);
}

test.describe('shared shell', () => {
  test('app host and published shell look the same', async ({page}) => {
    const markdown = '# 제목\n\n본문 **문장**이다.\n\n- 하나\n- 둘\n';
    await openApp(page, {markdown, context: {}});
    const app = await page.screenshot({fullPage: true});

    const site = fs.mkdtempSync(path.join(os.tmpdir(), 'madang-shell-'));
    const runtime = path.join(site, '_madang', 'runtime');
    fs.mkdirSync(path.dirname(runtime), {recursive: true});
    fs.symlinkSync(path.join(TEMPLATES, '_runtime'), runtime);
    const shell = fs.readFileSync(SHELL, 'utf8')
        .replace(/\$\{title\}/g, '문서')
        .replace(/\$\{base\}/g, '')
        .replace('${markdown}', () => JSON.stringify(markdown))
        .replace('${context}', () => '{}');
    fs.writeFileSync(path.join(site, 'index.html'), shell);
    await page.goto(pathToFileURL(path.join(site, 'index.html')).href);
    await expect(page.locator('#madang-page .madang-document')).toBeVisible();
    const published = await page.screenshot({fullPage: true});

    const ratio = await differingRatio(page, app, published);
    expect(ratio).toBeLessThanOrEqual(0.001);
    fs.rmSync(site, {recursive: true, force: true});
  });
});
