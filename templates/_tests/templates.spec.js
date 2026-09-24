const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const Ajv2020 = require('ajv/dist/2020');
const { TEMPLATES, NAMES, readJson, templateEntry, sample, openTemplate, events } = require('./harness');

const pathAttr = (p) => `[data-madang-path="${p}"]`;

test.describe('template files', () => {
  for (const name of NAMES) {
    test(`${name} has every file, no scripts and a CSP`, () => {
      for (const file of ['template.yaml', 'page.html', 'schema.json', 'sample.json', 'theme.json', 'preview.png']) {
        expect(fs.existsSync(path.join(TEMPLATES, name, file)), `${name}/${file}`).toBe(true);
      }
      const png = fs.readFileSync(path.join(TEMPLATES, name, 'preview.png'));
      expect(png.subarray(1, 4).toString()).toBe('PNG');

      const html = fs.readFileSync(path.join(TEMPLATES, name, 'page.html'), 'utf8');
      expect(html).not.toMatch(/<script/i);
      expect(html).not.toMatch(/\son[a-z]+\s*=/i);
      expect(html).toMatch(/http-equiv="Content-Security-Policy"[^>]*default-src 'none'/);

      const yaml = fs.readFileSync(path.join(TEMPLATES, name, 'template.yaml'), 'utf8');
      const entry = templateEntry(name);
      expect(yaml).toMatch(new RegExp(`^name: ${entry.name}$`, 'm'));
      expect(yaml).toMatch(new RegExp(`^version: ${entry.version}$`, 'm'));
      expect(yaml).toMatch(new RegExp(`^title: ${entry.title}$`, 'm'));
      const slotBlock = yaml.split(/^slots:\s*$/m)[1].split(/^\S/m)[0];
      const yamlSlots = [...slotBlock.matchAll(/^\s+([A-Za-z_][\w-]*):/gm)].map((m) => m[1]);
      expect(yamlSlots).toEqual(entry.slots.map((s) => s.name));

      const schema = readJson(path.join(TEMPLATES, name, 'schema.json'));
      const data = sample(name);
      const ajv = new Ajv2020({ strict: false });
      ajv.addSchema(schema, 'schema');
      for (const slot of entry.slots) {
        expect(schema[slot.schema.replace('#/', '')], `${name} schema for ${slot.name}`).toBeTruthy();
        if (data[slot.name] !== undefined) {
          const validate = ajv.getSchema(`schema${slot.schema}`);
          expect(validate(data[slot.name]), `${name} sample ${slot.name}: ${JSON.stringify(validate.errors)}`).toBe(true);
        }
        if (slot.required) expect(data[slot.name], `${name} sample for ${slot.name}`).toBeTruthy();
      }
    });
  }
});

test.describe('sample rendering', () => {
  test('table renders header and every row', async ({ page }) => {
    const { external } = await openTemplate(page, 'table');
    const data = sample('table').data;
    await expect(page.locator('th')).toHaveText(data.columns);
    await expect(page.locator('tbody tr')).toHaveCount(data.rows.length);
    await expect(page.locator(pathAttr('rows[1][0]'))).toHaveText('PostgreSQL');
    await expect(page.locator(pathAttr('rows[1][0]'))).toHaveAttribute('data-madang-slot', 'data');
    expect(external).toEqual([]);
  });

  test('decisions are grouped by state', async ({ page }) => {
    await openTemplate(page, 'decisions');
    await expect(page.locator('section.confirmed .card')).toHaveCount(1);
    await expect(page.locator('section.proposed .card')).toHaveCount(1);
    await expect(page.locator('section.deferred .card')).toHaveCount(1);
    await expect(page.locator('section.superseded .card')).toHaveCount(1);
    await expect(page.locator('section.confirmed ' + pathAttr('decisions[0].choice'))).toHaveText('refresh-lock');
    await expect(page.locator(pathAttr('decisions[0].options[2]'))).toHaveText('client-retry');
    await expect(page.locator('section.proposed ' + pathAttr('decisions[1].topic'))).toHaveText('세션 저장소');
  });

  test('tasks are split into status columns', async ({ page }) => {
    await openTemplate(page, 'tasks');
    await expect(page.locator('.todo .card')).toHaveCount(2);
    await expect(page.locator('.doing .card')).toHaveCount(1);
    await expect(page.locator('.blocked .card')).toHaveCount(1);
    await expect(page.locator('.done .card')).toHaveCount(2);
    await expect(page.locator('.doing ' + pathAttr('tasks[1].title'))).toHaveText('갱신 잠금');
    await expect(page.locator(pathAttr('tasks[1].due'))).toHaveText('2026-09-26');
    await expect(page.locator('.done .due')).toHaveCount(0);
  });

  test('resume renders base data', async ({ page }) => {
    await openTemplate(page, 'resume');
    await expect(page.locator('h1')).toHaveText('김마당');
    await expect(page.locator('.job')).toHaveCount(3);
    await expect(page.locator(pathAttr('work[1].company'))).toHaveText('펄어비스');
    await expect(page.locator('.skills li')).toHaveCount(5);
    await expect(page.locator(pathAttr('contact.links[0]') + ' a')).toHaveAttribute('href', 'https://github.com/madang');
  });

  test('theme variables reach the page', async ({ page }) => {
    await openTemplate(page, 'resume', { theme: { color: { accent: 'rgb(200, 0, 0)' }, font: { size: 18 } } });
    const style = await page.evaluate(() => {
      const h = getComputedStyle(document.querySelector('.headline'));
      return { color: h.color, size: getComputedStyle(document.body).fontSize };
    });
    expect(style).toEqual({ color: 'rgb(200, 0, 0)', size: '18px' });
  });
});

test.describe('slot overlay', () => {
  test('overlay overrides base and each value keeps its source slot', async ({ page }) => {
    await openTemplate(page, 'resume');
    const overlay = sample('resume').overlay;
    await expect(page.locator(pathAttr('title'))).toHaveText(overlay.title);
    await expect(page.locator(pathAttr('title'))).toHaveAttribute('data-madang-slot', 'overlay');
    await expect(page.locator(pathAttr('summary'))).toHaveAttribute('data-madang-slot', 'overlay');
    await expect(page.locator(pathAttr('name'))).toHaveAttribute('data-madang-slot', 'base');
    await expect(page.locator(pathAttr('work[1].company'))).toHaveAttribute('data-madang-slot', 'base');
    await expect(page.locator('h2').first()).toHaveAttribute('data-madang-slot', 'template');
  });

  test('objects merge deeply and arrays are replaced whole', async ({ page }) => {
    const base = sample('resume').base;
    const data = {
      base,
      overlay: {
        contact: { phone: '010-1111-2222' },
        work: [{ company: '넥슨', role: '리드', period: '2024 –' }]
      }
    };
    await openTemplate(page, 'resume', { data });
    await expect(page.locator(pathAttr('contact.phone'))).toHaveText('010-1111-2222');
    await expect(page.locator(pathAttr('contact.phone'))).toHaveAttribute('data-madang-slot', 'overlay');
    await expect(page.locator(pathAttr('contact.email'))).toHaveAttribute('data-madang-slot', 'base');
    await expect(page.locator('.job')).toHaveCount(1);
    await expect(page.locator(pathAttr('work[0].company'))).toHaveText('넥슨');
    await expect(page.locator(pathAttr('work[0].company'))).toHaveAttribute('data-madang-slot', 'overlay');
    expect(await page.evaluate(() => window.madang.sourceOf('skills[0]'))).toBe('base');
  });

  test('later slot in template order wins regardless of data key order', async ({ page }) => {
    const data = { overlay: { name: '덮어쓴 이름' }, base: { name: '원래 이름' } };
    await openTemplate(page, 'resume', { data });
    await expect(page.locator('h1')).toHaveText('덮어쓴 이름');
  });
});

test.describe('modes and selection', () => {
  test('edit mode click reports the data path', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'edit' });
    expect((await events(page, 'ready')).length).toBe(1);
    await page.locator(pathAttr('work[1].company')).click();
    const selected = await events(page, 'selected');
    expect(selected).toHaveLength(1);
    const p = selected[0].payload;
    expect(p.paths).toEqual(['work[1].company']);
    expect(p.slots).toEqual(['base']);
    expect(p.rects[0].width).toBeGreaterThan(0);
    expect(p.htmlFragment).toContain('펄어비스');
    expect(p.htmlFragment).toContain('data-madang-path="work[1].company"');
    await expect(page.locator('.madang-selected')).toHaveCount(1);
    const cursor = await page.locator(pathAttr('work[1].company')).evaluate((el) => getComputedStyle(el).cursor);
    expect(cursor).toBe('crosshair');
  });

  test('click on unbound child selects nearest path ancestor', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'edit' });
    await page.locator(pathAttr('work[1]') + ' .job-head').click({ position: { x: 350, y: 2 } });
    const last = (await events(page, 'selected')).pop().payload;
    expect(last.paths).toEqual(['work[1]']);
    expect(last.slots).toEqual(['base']);
  });

  test('ctrl/cmd click adds, escape clears', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'edit' });
    await page.locator(pathAttr('work[1].company')).click();
    await page.locator(pathAttr('work[0].company')).click({ modifiers: ['ControlOrMeta'] });
    let last = (await events(page, 'selected')).pop().payload;
    expect(last.paths).toEqual(['work[1].company', 'work[0].company']);
    await expect(page.locator('.madang-selected')).toHaveCount(2);
    await page.keyboard.press('Escape');
    last = (await events(page, 'selected')).pop().payload;
    expect(last.paths).toEqual([]);
    await expect(page.locator('.madang-selected')).toHaveCount(0);
  });

  test('fixed template text reports template as source', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'edit' });
    await page.locator('h2', { hasText: '경력' }).click();
    const last = (await events(page, 'selected')).pop().payload;
    expect(last.paths[0]).toMatch(/^template:/);
    expect(last.slots).toEqual(['template']);
  });

  test('view mode click does not select', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'view' });
    await page.locator(pathAttr('work[1].company')).click();
    expect(await events(page, 'selected')).toEqual([]);
    await expect(page.locator('.madang-selected')).toHaveCount(0);
  });

  test('view mode link click is reported as navigate', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'view' });
    const before = page.url();
    await page.locator('.contact a').click();
    const nav = await events(page, 'navigate');
    expect(nav.map((e) => e.payload.url)).toEqual(['https://github.com/madang']);
    expect(page.url()).toBe(before);
  });

  test('setMode switches behaviour and select() highlights by path', async ({ page }) => {
    await openTemplate(page, 'tasks', { mode: 'view' });
    await page.evaluate(() => window.madang.setMode('edit'));
    await expect(page.locator('html')).toHaveAttribute('data-madang-mode', 'edit');
    const info = await page.evaluate(() => window.madang.select(['tasks[1].title', 'tasks[2]']));
    expect(info.paths).toEqual(['tasks[1].title', 'tasks[2]']);
    await expect(page.locator('.madang-selected')).toHaveCount(2);
    await page.evaluate(() => window.madang.clearSelection());
    await expect(page.locator('.madang-selected')).toHaveCount(0);
    await page.evaluate(() => window.madang.setMode('view'));
    await page.locator(pathAttr('tasks[1].title')).click();
    expect(await events(page, 'selected')).toEqual([]);
  });

  test('hover in edit mode reports the path', async ({ page }) => {
    await openTemplate(page, 'decisions', { mode: 'edit' });
    await page.locator(pathAttr('decisions[1].topic')).hover();
    const hover = await events(page, 'hover');
    expect(hover.map((e) => e.payload.path)).toContain('decisions[1].topic');
    await page.mouse.move(1, 1);
    const after = await events(page, 'hover');
    expect(after[after.length - 1].payload.path).toBeNull();
  });
});

test.describe('data patching', () => {
  test('patchData updates the view immediately and keeps selection', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'edit' });
    await page.locator(pathAttr('work[1].company')).click();
    const res = await page.evaluate(() => window.madang.patchData('work[1].company', '펄어비스 (서울)'));
    expect(res).toEqual({ slot: 'base', path: 'work[1].company' });
    await expect(page.locator(pathAttr('work[1].company'))).toHaveText('펄어비스 (서울)');
    await expect(page.locator(pathAttr('work[1].company'))).toHaveClass(/madang-selected/);
    const data = await page.evaluate(() => window.madang.getData());
    expect(data.base.work[1].company).toBe('펄어비스 (서울)');
  });

  test('patchData writes to the slot that supplies the value', async ({ page }) => {
    await openTemplate(page, 'resume');
    const res = await page.evaluate(() => window.madang.patchData('title', '새 직함'));
    expect(res.slot).toBe('overlay');
    await expect(page.locator(pathAttr('title'))).toHaveText('새 직함');
    const data = await page.evaluate(() => window.madang.getData());
    expect(data.base.title).toBe(sample('resume').base.title);
  });

  test('patchData refuses fixed template text', async ({ page }) => {
    await openTemplate(page, 'resume', { mode: 'edit' });
    await page.locator('h2', { hasText: '경력' }).click();
    const tplPath = (await events(page, 'selected')).pop().payload.paths[0];
    const before = await page.evaluate(() => window.madang.getData());
    const res = await page.evaluate((p) => window.madang.patchData(p, '직장'), tplPath);
    expect(res).toBeNull();
    expect((await events(page, 'error')).pop().payload.message).toContain('template');
    expect(await page.evaluate(() => window.madang.getData())).toEqual(before);
  });

  test('patchData on table cell', async ({ page }) => {
    await openTemplate(page, 'table');
    await page.evaluate(() => window.madang.patchData('rows[0][1]', 2.2));
    await expect(page.locator(pathAttr('rows[0][1]'))).toHaveText('2.2');
  });
});

test.describe('bridge', () => {
  test('host adapter receives JSON messages', async ({ page }) => {
    await page.addInitScript(() => {
      window.__posted = [];
      window.madangBridge = { post: (json) => window.__posted.push(JSON.parse(json)) };
    });
    await openTemplate(page, 'resume', { mode: 'edit' });
    await page.locator(pathAttr('name')).click();
    const posted = await page.evaluate(() => window.__posted);
    expect(posted.map((m) => m.type)).toEqual(expect.arrayContaining(['ready', 'selected']));
    expect(posted.find((m) => m.type === 'selected').payload.paths).toEqual(['name']);
    expect(await events(page)).toEqual([]);
  });

  test('render errors are reported', async ({ page }) => {
    await openTemplate(page, 'resume');
    const ok = await page.evaluate(() =>
      window.madang.render({ name: 'x', slots: ['a'], html: '<p data-bind="nope.x"></p>' }, { a: {} }, {}, 'view')
    );
    expect(ok).toBe(false);
    const errors = await events(page, 'error');
    expect(errors[0].payload.message).toContain('unknown slot');
    const badMode = await page.evaluate(() => window.madang.render({ name: 'x', slots: ['a'], html: '<p></p>' }, { a: {} }, {}, 'bogus'));
    expect(badMode).toBe(false);
  });

  test('renderMarkdown falls back to plain text and accepts a renderer', async ({ page }) => {
    await openTemplate(page, 'table');
    await page.evaluate(() => window.madang.renderMarkdown('# 제목\n본문'));
    await expect(page.locator('pre.madang-md-plain')).toHaveText('# 제목\n본문');
    await page.evaluate(() => {
      window.madang.setMarkdownRenderer((src) => {
        const h = document.createElement('h1');
        h.textContent = src.replace(/^#\s*/, '');
        return h;
      });
      window.madang.renderMarkdown('# 다른 제목');
    });
    await expect(page.locator('h1')).toHaveText('다른 제목');
  });
});

test.describe('network isolation', () => {
  for (const name of NAMES) {
    test(`${name} makes no external requests`, async ({ page }) => {
      const { external } = await openTemplate(page, name, { mode: 'edit' });
      await page.evaluate(() => {
        const img = document.createElement('img');
        img.src = 'https://example.com/tracker.png';
        document.body.appendChild(img);
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://example.com/x.css';
        document.head.appendChild(link);
        return fetch('https://example.com/data.json').catch(() => null);
      });
      await page.waitForTimeout(200);
      expect(external).toEqual([]);
      const violations = await page.evaluate(() => window.__cspViolations || []);
      expect(violations.length).toBeGreaterThan(0);
    });
  }

  test('unsafe URLs are not written into attributes', async ({ page }) => {
    const data = sample('resume');
    data.base.contact.links = [{ label: 'x', url: 'javascript:alert(1)' }];
    await openTemplate(page, 'resume', { data });
    await expect(page.locator('.contact a')).not.toHaveAttribute('href', /.+/);
  });
});
