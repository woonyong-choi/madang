// 게시한 사이트의 페이지를 브라우저로 열어 렌더된 모습을 JSON으로 출력한다.
// 사용: NODE_PATH=<templates/_tests/node_modules> node open_site.js <url>...
'use strict';

const {chromium} = require('@playwright/test');

async function inspect(browser, url) {
  const page = await browser.newPage();
  const origin = new URL(url).origin;
  const outside = [];
  const errors = [];
  page.on('request', (request) => {
    const target = new URL(request.url());
    const local = ['file:', 'about:', 'data:'].includes(target.protocol) ||
        target.origin === origin;
    if (!local) outside.push(request.url());
  });
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(url);
  await page.waitForSelector('.madang-document');
  const frame = page.frameLocator('iframe.madang-view-frame').first();
  const frames = await page.locator('iframe.madang-view-frame').count();
  const result = {
    url: url,
    heading: await page.locator('.madang-document h1').first().innerText(),
    frames: frames,
    viewText: frames ? await frame.locator('body').innerText() : null,
    fallbacks: await page.locator('.madang-view-fallback')
        .evaluateAll((els) => els.map((el) => el.dataset.status)),
    links: await page.locator('.madang-document a')
        .evaluateAll((els) => els.map((el) => el.getAttribute('href'))),
    outside: outside,
    errors: errors,
  };
  await page.close();
  return result;
}

(async () => {
  const browser = await chromium.launch();
  try {
    const results = [];
    for (const url of process.argv.slice(2)) {
      results.push(await inspect(browser, url));
    }
    process.stdout.write(JSON.stringify(results));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
