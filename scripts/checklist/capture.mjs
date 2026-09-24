/**
 * @fileoverview 앱 문서 탭 호스트(app.html)와 게시 페이지를 같은 창 크기의
 * 헤드리스 Chromium에서 그려 스크린샷 픽셀을 비교한다.
 *
 * 사용: node capture.mjs --app <app.html> --payload <payload.json>
 *           --site <게시된 문서.html> --out <폴더> [--expect <글자>]...
 *
 * payload.json은 앱이 madangApp.render()에 넘기는 값({markdown, context, base})
 * 이다. 결과는 JSON 한 줄로 표준 출력에 쓴다. 비교는 문서 영역(#madang-page)과
 * 창 전체 두 가지이며, 각 스크린샷과 차이 이미지를 --out 폴더에 남긴다.
 */

import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';

import pixelmatch from 'pixelmatch';
import {chromium} from 'playwright';
import {PNG} from 'pngjs';

const VIEWPORT = {width: 1000, height: 1400};
// pixelmatch의 색 차이 허용값(0~1). 글꼴 안티앨리어싱 정도만 넘긴다.
const COLOR_THRESHOLD = 0.1;
const SETTLE_POLL_MS = 250;
const SETTLE_ROUNDS = 4;
const SETTLE_LIMIT_MS = 15000;

const {values: args} = parseArgs({
  options: {
    app: {type: 'string'},
    payload: {type: 'string'},
    site: {type: 'string'},
    out: {type: 'string'},
    expect: {type: 'string', multiple: true, default: []},
  },
});

/**
 * 문서와 뷰어 iframe의 높이가 몇 번 연달아 같을 때까지 기다린다.
 * @param {!Object} page Playwright 페이지.
 * @return {!Promise<boolean>} 시간 안에 멈췄으면 참.
 */
async function settle(page) {
  const started = Date.now();
  let last = '';
  let same = 0;
  while (Date.now() - started < SETTLE_LIMIT_MS) {
    const now = await page.evaluate(() => JSON.stringify([
      document.documentElement.scrollHeight,
      Array.from(document.querySelectorAll('iframe'),
          (frame) => frame.style.height || ''),
    ]));
    same = now === last ? same + 1 : 0;
    last = now;
    if (same >= SETTLE_ROUNDS) return true;
    await page.waitForTimeout(SETTLE_POLL_MS);
  }
  return false;
}

/**
 * 페이지와 그 안 모든 iframe의 보이는 글자를 모은다.
 * @param {!Object} page Playwright 페이지.
 * @return {!Promise<string>} 이어 붙인 글자.
 */
async function visibleText(page) {
  const parts = [];
  for (const frame of page.frames()) {
    try {
      parts.push(await frame.evaluate(() => document.body.innerText));
    } catch {
      // 비어 있거나 떨어져 나간 iframe은 건너뛴다.
    }
  }
  return parts.join('\n');
}

/**
 * 한 화면을 찍는다.
 * @param {!Object} page Playwright 페이지.
 * @param {string} name 파일 이름 앞부분.
 * @return {!Promise<!Object>} 스크린샷과 글자.
 */
async function shoot(page, name) {
  const settled = await settle(page);
  const element = await page.locator('#madang-page').screenshot();
  const full = await page.screenshot({fullPage: true});
  writeFileSync(join(args.out, `${name}-document.png`), element);
  writeFileSync(join(args.out, `${name}-full.png`), full);
  return {settled, element, full, text: await visibleText(page)};
}

/**
 * 두 PNG를 픽셀 단위로 비교하고 차이 이미지를 남긴다.
 * @param {!Buffer} left 앱 쪽 PNG.
 * @param {!Buffer} right 게시 쪽 PNG.
 * @param {string} name 차이 이미지 이름.
 * @return {!Object} 크기, 다른 픽셀 수, 비율.
 */
function compare(left, right, name) {
  const a = PNG.sync.read(left);
  const b = PNG.sync.read(right);
  const sizes = {app: [a.width, a.height], site: [b.width, b.height]};
  if (a.width !== b.width || a.height !== b.height) {
    return {sameSize: false, sizes, diffPixels: null, ratio: 1};
  }
  const diff = new PNG({width: a.width, height: a.height});
  const diffPixels = pixelmatch(
      a.data, b.data, diff.data, a.width, a.height,
      {threshold: COLOR_THRESHOLD});
  writeFileSync(join(args.out, `${name}-diff.png`), PNG.sync.write(diff));
  return {
    sameSize: true,
    sizes,
    diffPixels,
    ratio: diffPixels / (a.width * a.height),
  };
}

/**
 * 앱 호스트와 게시 페이지를 그려 비교한 결과를 낸다.
 * @return {!Promise<!Object>} 비교 결과.
 */
async function main() {
  mkdirSync(args.out, {recursive: true});
  const payload = JSON.parse(readFileSync(args.payload, 'utf8'));
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext(
        {viewport: VIEWPORT, deviceScaleFactor: 1});
    const external = [];
    context.on('request', (request) => {
      if (/^https?:/.test(request.url())) external.push(request.url());
    });

    const appPage = await context.newPage();
    await appPage.goto(`${pathToFileURL(args.app).href}?doc=1`);
    await appPage.waitForFunction(() => Boolean(window.madangApp));
    await appPage.evaluate((value) => window.madangApp.render(value), payload);
    const app = await shoot(appPage, 'app');

    const sitePage = await context.newPage();
    await sitePage.goto(pathToFileURL(args.site).href);
    const site = await shoot(sitePage, 'site');

    const expected = Object.fromEntries(args.expect.map((word) => [
      word, {app: app.text.includes(word), site: site.text.includes(word)},
    ]));
    return {
      viewport: VIEWPORT,
      colorThreshold: COLOR_THRESHOLD,
      settled: {app: app.settled, site: site.settled},
      document: compare(app.element, site.element, 'document'),
      full: compare(app.full, site.full, 'full'),
      expected,
      externalRequests: external,
    };
  } finally {
    await browser.close();
  }
}

main().then(
    (result) => process.stdout.write(JSON.stringify(result) + '\n'),
    (error) => {
      process.stderr.write(`${error.stack || error}\n`);
      process.exit(1);
    });
