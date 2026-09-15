// Local-only browser regression. No point-site, analytics, or AI requests.
// PLAYWRIGHT_MODULE and BROWSER_EXECUTABLE select installed test tools.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../_site');
const baseline = process.env.BASELINE_ROOT;
const fontDir = process.env.QA_FONT_DIR;
const pages = ['index.html', 'offers.html', 'guides.html', 'game.html?game=Township',
  'houchishojo-guide.html', 'evertale-guide.html', 'atlas-earth-guide.html',
  'family-farm-adventure-guide.html', 'klondike-adventures-guide.html',
  'merge-help-guide.html', 'magic-jigsaw-puzzles-guide.html', 'puzzles-survival-guide.html',
  'township-lv60.html', 'township-lv70.html'];
const server = http.createServer((req, res) => {
  const prefix = baseline && req.url.startsWith('/__baseline__/') ? '/__baseline__' : fontDir && req.url.startsWith('/__font__/') ? '/__font__' : '';
  const source = prefix === '/__baseline__' ? baseline : prefix === '/__font__' ? fontDir : root;
  const file = path.resolve(source, '.' + decodeURI(req.url.split('?')[0].slice(prefix.length)));
  if (!file.startsWith(source + path.sep)) { res.writeHead(403).end(); return; }
  try {
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' :
      file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'application/octet-stream');
    res.end(fs.readFileSync(file));
  } catch { res.writeHead(404).end(); }
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({executablePath: process.env.BROWSER_EXECUTABLE,
    args: ['--no-sandbox', '--disable-dev-shm-usage'], headless: true});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
    if (fontDir) {
      await page.addInitScript(({origin}) => document.addEventListener('DOMContentLoaded', () => {
        const link = document.createElement('link'); link.rel = 'stylesheet'; link.href = origin + '/__font__/400.css'; document.head.appendChild(link);
        const style = document.createElement('style'); style.textContent = 'body {font-family:"Noto Sans JP",sans-serif!important}'; document.head.appendChild(style);
      }), {origin});
    }
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const baselineOverflows = [];
    let checks = 0;
    for (const width of [375, 390, 430, 768]) {
      await page.setViewportSize({width, height: 844});
      for (const name of pages) {
        await page.goto(`${origin}/${name}`, {waitUntil: 'networkidle'});
        const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
        if (scroll > width + 1) {
          assert.ok(baseline, `${name} overflow at ${width}; set BASELINE_ROOT to compare`);
          await page.goto(`${origin}/__baseline__/${name}`, {waitUntil: 'networkidle'});
          const old = await page.evaluate(() => document.documentElement.scrollWidth);
          assert.ok(scroll <= old, `${name} introduces overflow at ${width}`);
          baselineOverflows.push({name, width, scroll, baseline: old});
          await page.goto(`${origin}/${name}`, {waitUntil: 'networkidle'});
        }
        if (name.includes('-guide.html') || name.startsWith('township-lv')) {
          assert.equal(await page.locator('#current-verified-offers').count(), 1, name);
          assert.match(await page.locator('#current-verified-offers').innerText(), /円|確認済みの案件データはありません/, name);
        }
        checks++;
      }
    }
    assert.deepEqual(errors, []);
    // A changed CSV must update a guide without rewriting its historical body.
    const before = fs.readFileSync(path.join(root, 'data/published_offers.csv'), 'utf8');
    const modified = before.replace(/(エバーテイル,[^\n]*?,)(\d+)(,)/, '$199999$3');
    assert.notEqual(modified, before);
    await page.route('**/data/published_offers.csv', route => route.fulfill({status: 200, body: modified}));
    for (const name of ['evertale-guide.html', 'index.html', 'offers.html', 'game.html?game=' + encodeURIComponent('エバーテイル')]) {
      await page.goto(`${origin}/${name}`, {waitUntil: 'networkidle'});
      assert.match(await page.locator(name.includes('-guide') ? '#current-verified-offers' : 'body').innerText(), /99,999\s*円/, name);
    }
    if (process.env.QA_SCREENSHOT) {
      await page.goto(`${origin}/evertale-guide.html`, {waitUntil: 'networkidle'});
      await page.locator('#current-verified-offers').screenshot({path: process.env.QA_SCREENSHOT});
    }
    console.log(JSON.stringify({pages: pages.length, widths: 4, checks, pageErrors: errors.length, amountPropagation: true, baselineOverflows}));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(() => server.close());
