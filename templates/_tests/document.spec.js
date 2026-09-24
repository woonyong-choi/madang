const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const {test, expect} = require('@playwright/test');
const {TEMPLATES, readJson, trackExternal} = require('./harness');
const renderer = require('../_runtime/document.js');

const HOST = path.join(__dirname, 'fixtures', 'document.html');
const RESUME = path.join(TEMPLATES, 'viewers', 'resume-basic');
const RESUME_HTML = fs.readFileSync(path.join(RESUME, 'index.html'), 'utf8');
const RESUME_SAMPLE = readJson(path.join(RESUME, 'sample.json'));
const RESUME_KEY = 'resume/basic data=./base.json';
const RESUME_FENCE = '```view ' + RESUME_KEY + '\n```\n';

/**
 * 문서 호스트 페이지를 열고 renderDocument() 결과를 #doc에 넣는다.
 *
 * @param {!Object} page Playwright 페이지.
 * @param {string} markdown 마크다운 원문.
 * @param {!Object=} context 렌더러 context.
 * @return {!Promise<{external: !Array<string>, result: !Object}>} 로컬이 아닌
 *     요청 URL과 렌더 결과.
 */
async function openDocument(page, markdown, context = {}) {
  const external = trackExternal(page);
  await page.goto(pathToFileURL(HOST).href);
  const result = await page.evaluate(([md, ctx]) => {
    const target = document.getElementById('doc');
    return window.madangDocument.mountDocument(target, md, ctx);
  }, [markdown, context]);
  return {external, result};
}

/**
 * @param {*} data 뷰어에 넘길 데이터.
 * @param {!Object=} tokens 앱 토큰.
 * @return {!Object} 이력서 뷰어 하나가 "ok"인 context.
 */
function resumeContext(data, tokens) {
  return {
    views: {[RESUME_KEY]: {status: 'ok', html: RESUME_HTML, data: data}},
    tokens: tokens,
  };
}

const MARKDOWN = [
  '---',
  'title: 이력서 정리',
  'tags: [resume]',
  '---',
  '# 제목',
  '',
  '| 회사 | 기간 |',
  '|---|---|',
  '| 한빛 | 2022 |',
  '',
  '```js',
  'const tag = "<b>";',
  '```',
  '',
  '<script>window.injected = true</script>',
  '',
  '[나쁜 링크](javascript:alert(1)) [좋은 링크](https://example.com/)',
  '',
].join('\n');

test.describe('markdown', () => {
  test('front matter, tables and code are rendered', async ({page}) => {
    const {result} = await openDocument(page, MARKDOWN);
    expect(result.frontMatter).toBe('title: 이력서 정리\ntags: [resume]');
    const doc = page.locator('#doc .madang-document');
    await expect(doc.locator('details.madang-frontmatter code'))
        .toHaveText('title: 이력서 정리\ntags: [resume]');
    await expect(doc.locator('h1')).toHaveText('제목');
    await expect(doc.locator('hr')).toHaveCount(0);
    await expect(doc.locator('table th')).toHaveText(['회사', '기간']);
    await expect(doc.locator('table td')).toHaveText(['한빛', '2022']);
    await expect(doc.locator('pre code.language-js'))
        .toHaveText('const tag = "<b>";');
  });

  test('raw html and unsafe links stay text', async ({page}) => {
    await openDocument(page, MARKDOWN);
    const doc = page.locator('#doc');
    await expect(doc.locator('script')).toHaveCount(0);
    await expect(doc).toContainText('<script>window.injected = true</script>');
    expect(await page.evaluate(() => window.injected)).toBeUndefined();
    await expect(doc.locator('a')).toHaveCount(1);
    await expect(doc.locator('a')).toHaveAttribute(
        'href', 'https://example.com/');
    await expect(doc).toContainText('나쁜 링크');
  });

  test('node and browser produce the same html', async ({page}) => {
    const context = resumeContext(RESUME_SAMPLE, {accent: '#123456'});
    const markdown = MARKDOWN + RESUME_FENCE;
    const {result} = await openDocument(page, markdown, context);
    expect(result.html).toBe(renderer.renderDocument(markdown, context).html);
    expect(renderer.listViews(markdown)).toEqual([{
      key: RESUME_KEY,
      name: 'resume/basic',
      pin: null,
      data: './base.json',
    }]);
  });

  test('madang runtime renders markdown with the renderer', async ({page}) => {
    await openDocument(page, '');
    const same = await page.evaluate((md) => {
      const target = document.getElementById('doc');
      const ok = window.madang.renderMarkdown(md, {target: target});
      const direct = document.createElement('div');
      direct.innerHTML = window.madang.renderDocument(md).html;
      return ok && direct.innerHTML === target.innerHTML;
    }, MARKDOWN);
    expect(same).toBe(true);
  });
});

test.describe('view fence', () => {
  test('ok view is a sandboxed iframe with its data', async ({page}) => {
    await openDocument(page, RESUME_FENCE, resumeContext(RESUME_SAMPLE));
    const frame = page.locator('iframe.madang-view-frame');
    await expect(frame).toHaveCount(1);
    await expect(frame).toHaveAttribute('sandbox', 'allow-scripts');
    const view = page.frameLocator('iframe.madang-view-frame');
    await expect(view.locator('h1')).toHaveText(RESUME_SAMPLE.name);
    await expect(view.locator('.job')).toHaveCount(RESUME_SAMPLE.work.length);
    const parentAccess = await page.frames()[1].evaluate(() => {
      try {
        return parent.document.title;
      } catch {
        return 'blocked';
      }
    });
    expect(parentAccess).toBe('blocked');
    await expect(frame).toHaveAttribute('style', /height: \d+px/);
  });

  test('app tokens are injected and win over the viewer', async ({page}) => {
    const html = '<!doctype html><html><head><style>' +
        ':root{--app-accent:red !important;--app-bg:blue}' +
        'p{color:var(--app-accent);background:var(--app-bg)}' +
        '</style></head><body><p>x</p></body></html>';
    const context = {
      views: {'demo/tokens': {status: 'ok', html: html, data: null}},
      tokens: {accent: '#123456', bg: 'red;}p{display:none', radius: '4px'},
    };
    await openDocument(page, '```view demo/tokens\n```\n', context);
    const view = page.frameLocator('iframe.madang-view-frame');
    await expect(view.locator('p')).toHaveCSS('color', 'rgb(18, 52, 86)');
    await expect(view.locator('p')).toBeVisible();
    await expect(view.locator('p'))
        .toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    const radius = await page.frames()[1].evaluate(() => {
      return getComputedStyle(document.documentElement)
          .getPropertyValue('--app-radius').trim();
    });
    expect(radius).toBe('4px');
  });

  test('schema mismatch falls back to a data table', async ({page}) => {
    const data = {name: 7, work: [{role: '엔지니어'}]};
    const context = {
      views: {
        [RESUME_KEY]: {
          status: 'invalid',
          data: data,
          errors: [
            {path: 'name', message: 'expected string, got number'},
            {path: 'work[0].company', message: 'is required'},
          ],
        },
      },
    };
    await openDocument(page, RESUME_FENCE, context);
    await expect(page.locator('iframe')).toHaveCount(0);
    const figure = page.locator('figure.madang-view-fallback');
    await expect(figure).toHaveAttribute('data-status', 'invalid');
    await expect(figure.locator('figcaption')).toContainText('스키마');
    await expect(figure.locator('.madang-view-errors code'))
        .toHaveText(['name', 'work[0].company']);
    await expect(figure.locator('table.madang-data th[scope="row"]').first())
        .toHaveText('name');
    await expect(figure.locator('table.madang-data table th[scope="col"]'))
        .toHaveText(['role']);
    await expect(figure).toContainText('엔지니어');
  });

  test('broken and unknown views fall back too', async ({page}) => {
    const markdown = RESUME_FENCE + '```view demo/unknown\n```\n';
    const context = {
      views: {
        [RESUME_KEY]: {
          status: 'broken',
          data: {name: '김마당'},
          message: 'source missing',
        },
      },
    };
    await openDocument(page, markdown, context);
    await expect(page.locator('iframe')).toHaveCount(0);
    const figures = page.locator('figure.madang-view-fallback');
    await expect(figures).toHaveCount(2);
    await expect(figures.nth(0)).toHaveAttribute('data-status', 'broken');
    await expect(figures.nth(0)).toContainText('끊겨');
    await expect(figures.nth(0)).toContainText('김마당');
    await expect(figures.nth(1)).toHaveAttribute('data-status', 'missing');
    await expect(figures.nth(1)).toContainText('데이터 없음');
  });
});

test.describe('network isolation', () => {
  test('renderer and views make no external requests', async ({page}) => {
    const html = '<!doctype html><html><head>' +
        '<link rel="stylesheet" href="https://example.com/v.css">' +
        '</head><body><img src="https://example.com/v.png"><script>' +
        'fetch("https://example.com/v.json").catch(function() {});' +
        '</script></body></html>';
    const markdown = '![원격](https://example.com/remote.png)\n\n' +
        '```view demo/net\n```\n';
    const context = {views: {'demo/net': {status: 'ok', html: html}}};
    const {external} = await openDocument(page, markdown, context);
    await expect(page.locator('#doc img')).toHaveCount(0);
    await expect(page.locator('a.madang-remote-image')).toHaveText('원격');
    await page.waitForTimeout(300);
    expect(external).toEqual([]);
  });

  test('marked is vendored from the pinned package', () => {
    const vendored = path.join(TEMPLATES, '_runtime', 'vendor');
    const pkg = require.resolve('marked/package.json');
    const version = readJson(pkg).version;
    expect(readJson(path.join(__dirname, 'package.json'))
        .devDependencies.marked).toBe(version);
    expect(fs.readFileSync(path.join(vendored, 'marked.umd.js')))
        .toEqual(fs.readFileSync(
            path.join(path.dirname(pkg), 'lib', 'marked.umd.js')));
    expect(fs.readFileSync(path.join(vendored, 'marked.LICENSE'), 'utf8'))
        .toContain('MIT');
  });
});
