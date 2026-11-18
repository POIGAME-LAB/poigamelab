// Local-only browser regression for the shared load states on index / offers / game.
// Serves the built _site (run the deploy build steps first). Network calls to point
// sites, analytics and ads are blocked; data responses are rewritten in the browser.
//
// Scenarios: normal, verified-0 (empty CSV), published CSV download failure, every
// data file failing, refresh status missing (partial failure), stale data (old run
// and old confirmation dates), JavaScript disabled, and a phone viewport.
//
// Nothing pins an amount, a row count or a game list: expectations are derived from
// the served CSV files. Run: node tests/test_load_states_browser.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium, devices } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../_site');
const SHOTS = process.env.SCREENSHOT_DIR || '';

const server = http.createServer((req, res) => {
  const file = path.resolve(root, '.' + decodeURI(req.url.split('?')[0]));
  if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
  try {
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' :
      file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.json') ? 'application/json' :
      file.endsWith('.css') ? 'text/css' : 'text/plain; charset=utf-8');
    res.end(fs.readFileSync(file));
  } catch { res.writeHead(404).end(); }
});

const publishedText = fs.readFileSync(path.join(root, 'data/published_offers.csv'), 'utf8');
const header = publishedText.split(/\r?\n/)[0];
const verifiedGameNames = (() => {
  const lines = publishedText.trim().split(/\r?\n/).slice(1);
  return new Set(lines.map(line => line.split(',')[1]).filter(Boolean));
})();

// Shift every confirmation date far into the past (keeps the CSV otherwise intact).
const agedCsv = publishedText.replace(/,(\d{4}-\d{2}-\d{2}),https?:/g, ',2026-01-05,https:');

const SCENARIOS = {
  normal: {},
  empty: { 'data/published_offers.csv': { status: 200, body: header + '\n' } },
  offersFailed: { 'data/published_offers.csv': { status: 500, body: '' } },
  allFailed: {
    'data/published_offers.csv': { status: 500, body: '' },
    'games.csv': { status: 500, body: '' },
    'data/refresh_status.json': { status: 500, body: '' },
    'config/refresh_policy.json': { status: 500, body: '' }
  },
  partial: { 'data/refresh_status.json': { status: 404, body: '' } },
  stale: {
    'data/published_offers.csv': { status: 200, body: agedCsv },
    'data/refresh_status.json': {
      status: 200,
      body: JSON.stringify({ success: true, startedAt: '2026-01-05T00:00:00Z', finishedAt: '2026-01-05T00:00:00Z',
        results: [{ game: 'Township', returncode: 0, publishableCount: 2, collectionComplete: true, degradedReasons: [] }] })
    }
  }
};

const TOWNSHIP = 'game.html?game=Township';
const NO_OFFER_GAME = [...fs.readFileSync(path.join(root, 'games.csv'), 'utf8').split(/\r?\n/).slice(1)]
  .map(line => line.split(',')[0]).find(name => name && !verifiedGameNames.has(name));

async function open(context, url, overrides) {
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.route(/googletagmanager|googlesyndication|google-analytics|doubleclick|^https:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  await page.route('**/*', async route => {
    const rel = new URL(route.request().url()).pathname.replace(/^\//, '');
    const hit = overrides[rel];
    if (hit) return route.fulfill({ status: hit.status, body: hit.body, contentType: 'text/plain; charset=utf-8' });
    return route.fallback();
  });
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(900);
  return { page, errors };
}

const visible = page => page.evaluate(() => document.body.innerText);
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);

(async () => {
  assert.ok(NO_OFFER_GAME, 'need a game without verified offers');
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {});
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks += 1; };

  for (const [name, overrides] of Object.entries(SCENARIOS)) {
    for (const viewport of ['desktop', 'phone']) {
      const context = await browser.newContext(viewport === 'phone' ? { ...devices['iPhone 13'] } : { viewport: { width: 1280, height: 900 } });
      for (const target of ['index.html', 'offers.html', TOWNSHIP, `game.html?game=${encodeURIComponent(NO_OFFER_GAME)}`]) {
        const { page, errors } = await open(context, base + target, overrides);
        const text = await visible(page);
        const label = `${name}/${viewport}/${target}`;
        ok(errors.length === 0, `${label}: page errors ${errors.join(' | ')}`);
        ok(!(await overflow(page)), `${label}: horizontal overflow`);
        ok(!text.includes('読み込み中'), `${label}: loading text left after load`);
        // "確認中" must never be the answer to "how much / when" on these pages.
        const mainText = text.replace(/一次情報を確認中/g, '');
        ok(!/最高還元\s*確認中|最終更新\s*確認中|：確認中/.test(mainText), `${label}: open-ended 確認中 shown`);
        ok(!mainText.includes('掲載情報を確認中'), `${label}: perpetual 掲載情報を確認中 shown`);

        if (name === 'offersFailed' || name === 'allFailed') {
          ok(text.includes('最新情報を取得できませんでした'), `${label}: failure not stated`);
          ok(!text.includes('現在、確認済み案件の掲載はありません'), `${label}: failure shown as empty`);
          ok(!text.includes('検証済みの案件がありません'), `${label}: failure shown as no verified offers`);
        }
        if (name === 'empty') {
          ok(!text.includes('最新情報を取得できませんでした'), `${label}: empty shown as failure`);
          if (target === 'index.html' || target === 'offers.html') {
            ok(text.includes('現在、確認済み案件の掲載はありません'), `${label}: empty state not stated`);
          }
        }
        if (name === 'normal' && target === TOWNSHIP) {
          ok(/\d{1,3}(,\d{3})*円/.test(text), `${label}: verified amount missing`);
          ok(/確認/.test(text) && /\d{4}-\d{2}-\d{2}/.test(text), `${label}: confirmation date missing`);
        }
        if (name === 'normal' && target === 'index.html') {
          const stat = await page.textContent('#statMaxReward');
          ok(/\d円|\d 円/.test(stat), `${label}: dashboard max reward is "${stat}"`);
          ok(/\d{4}\/\d{2}\/\d{2}/.test(await page.textContent('#statUpdated')), `${label}: dashboard date`);
        }
        if (name === 'stale' && (target === 'index.html' || target === TOWNSHIP)) {
          ok(/最終確認|現在の掲載は未確認|日以上経過|最終確認データを掲載中/.test(text), `${label}: stale data not flagged`);
        }
        if (SHOTS && ['normal', 'offersFailed', 'empty', 'stale'].includes(name) && target !== `game.html?game=${encodeURIComponent(NO_OFFER_GAME)}`) {
          const file = `${name}-${viewport}-${target.replace(/[^a-z0-9]+/gi, '_')}.png`;
          await page.screenshot({ path: path.join(SHOTS, file), fullPage: viewport === 'desktop' });
        }
        await page.close();
      }
      await context.close();
    }
  }

  // Guide pages: the live "現在の確認済み案件" panel uses the same states.
  const guideContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  for (const [name, expectText, forbidText] of [
    ['normal', /円 · /, /取得できませんでした|読み込み中/],
    ['empty', /現在、確認済み案件の掲載はありません/, /取得できませんでした/],
    ['offersFailed', /最新情報を取得できませんでした/, /掲載はありません|案件データはありません/]
  ]) {
    const { page, errors } = await open(guideContext, base + 'kingshot-guide.html', SCENARIOS[name]);
    const panel = await page.locator('#current-verified-offers').innerText();
    ok(errors.length === 0, `guide/${name}: page errors`);
    ok(expectText.test(panel), `guide/${name}: panel "${panel.slice(0, 120)}"`);
    ok(!forbidText.test(panel), `guide/${name}: wrong state in panel`);
    await page.close();
  }
  {
    const { page } = await open(guideContext, base + 'family-farm-adventure-guide.html', {});
    const panel = await page.locator('#current-verified-offers').innerText();
    ok(!/ポイントサイト · \d/.test(panel), 'guide panel: unnamed point site');
    await page.close();
  }
  await guideContext.close();

  // JavaScript disabled: the first HTML must already carry the comparison values.
  const nojs = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1280, height: 900 } });
  const indexPage = await nojs.newPage();
  await indexPage.goto(base + 'index.html');
  const indexText = await visible(indexPage);
  ok(!indexText.includes('確認中'), 'nojs index: 確認中 in first HTML');
  ok(/\d{1,3}(,\d{3})* 円/.test(await indexPage.textContent('#statMaxReward')), 'nojs index: dashboard amount');
  ok(/確認/.test(indexText), 'nojs index: confirmation dates');
  const offersPage = await nojs.newPage();
  await offersPage.goto(base + 'offers.html');
  const offersText = await visible(offersPage);
  ok(/\d{1,3}(,\d{3})* 円/.test(offersText) && /確認済み案件/.test(offersText), 'nojs offers: verified figures');
  await nojs.close();

  await browser.close();
  server.close();
  console.log(`load-state browser checks: ${checks} PASS`);
})().catch(error => { console.error(error); process.exit(1); });
