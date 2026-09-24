// Regenerates <template>/preview.png from each template's sample data.
const path = require('path');
const {chromium} = require('@playwright/test');
const {TEMPLATES, NAMES, openTemplate} = require('./harness');

(async () => {
  const browser = await chromium.launch();
  try {
    for (const name of NAMES) {
      const page = await browser.newPage({
        viewport: {width: 1000, height: 760},
        deviceScaleFactor: 1,
      });
      await openTemplate(page, name);
      const out = path.join(TEMPLATES, name, 'preview.png');
      await page.screenshot({path: out, fullPage: true});
      await page.close();
      console.log('wrote', path.relative(TEMPLATES, out));
    }
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
