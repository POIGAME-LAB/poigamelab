// Local-only browser regression for game.html when a game has no verified offer.
// Serves the built _site (run `python scripts/build_public_site.py` first). No point-site,
// analytics or AI requests. PLAYWRIGHT_MODULE and BROWSER_EXECUTABLE select installed tools.
//
// Nothing here pins a row count, a game list or an amount: the games without a verified offer
// are derived from the served games.csv / published_offers.csv, and the "offers appear /
// disappear" cases are produced by rewriting the CSV response in the browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../_site');

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

function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') quoted = false; else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}
const quote = value => /[",\n]/.test(value) ? `"${String(value).replace(/"/g, '""')}"` : String(value);
const toCsv = rows => rows.map(r => r.map(quote).join(',')).join('\n') + '\n';

(async () => {
  const published = parseCsv(fs.readFileSync(path.join(root, 'data/published_offers.csv'), 'utf8'));
  const header = published[0];
  const col = name => header.indexOf(name);
  const body = published.slice(1).filter(r => r.length === header.length);
  const catalog = parseCsv(fs.readFileSync(path.join(root, 'games.csv'), 'utf8'));
  const names = catalog.slice(1).map(r => r[catalog[0].indexOf('name')]).filter(Boolean);
  const verifiedGames = new Set(body.filter(r => r[col('verified')].toLowerCase() === 'true').map(r => r[col('game')]));
  const noOffer = names.filter(n => !verifiedGames.has(n));
  const withOffer = names.filter(n => verifiedGames.has(n));
  assert.ok(noOffer.length > 0 && withOffer.length > 0, 'need both kinds of games to exercise the toggle');

  const guides = fs.readFileSync(path.join(root, 'site-guides.js'), 'utf8');
  const slugOf = name => {
    const at = guides.indexOf(`"${name}": {`);
    if (at < 0) return '';
    const m = guides.slice(at, at + 1500).match(/href: "([a-z0-9-]+)-guide\.html"/);
    return m ? m[1] : '';
  };

  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE, args: ['--no-sandbox', '--disable-dev-shm-usage'], headless: true });
  let checks = 0;
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const open = async (game, csv) => {
      await page.unroute('**/data/published_offers.csv').catch(() => {});
      if (csv) await page.route('**/data/published_offers.csv', route => route.fulfill({ status: 200, contentType: 'text/csv', body: csv }));
      await page.goto(`${origin}/game.html?game=${encodeURIComponent(game)}`, { waitUntil: 'networkidle' });
    };
    const state = () => page.evaluate(() => ({
      boxVisible: !document.getElementById('noVerifiedOffer').hidden,
      lead: document.getElementById('noVerifiedLead').innerText,
      records: document.getElementById('noVerifiedRecords').hidden ? '' : document.getElementById('noVerifiedRecords').innerText,
      links: [...document.querySelectorAll('#noVerifiedLinks a')].map(a => a.getAttribute('href')),
      best: document.getElementById('bestReward').innerText,
      title: document.title,
      canonical: document.querySelector('link[rel="canonical"]')?.href || '',
      description: document.querySelector('meta[name="description"]')?.content || '',
      text: document.body.innerText,
    }));

    for (const [label, size] of [['pc', { width: 1280, height: 900 }], ['sp', { width: 390, height: 844 }]]) {
      await page.setViewportSize(size);
      // 1. every catalog game without a verified offer
      for (const game of noOffer) {
        await open(game);
        const s = await state();
        assert.equal(s.boxVisible, true, `${game}: notice must be visible`);
        assert.match(s.lead, /案件が存在しないとは断定していません/, game);
        assert.doesNotMatch(s.text, /確認できる案件なし|現在掲載なし/, game);
        assert.ok(s.links.includes('offers.html') && s.links.includes('guides.html'), game);
        assert.ok(s.title.startsWith(game), `${game}: title`);
        assert.ok(s.canonical.includes('game.html?game='), `${game}: canonical`);
        assert.doesNotMatch(s.description, /\d+件の掲載枠/, `${game}: description must not count unverified rows`);
        const slug = slugOf(game);
        if (slug && fs.existsSync(path.join(root, `data/guide-experiences/${slug}.json`))) {
          const players = JSON.parse(fs.readFileSync(path.join(root, `data/guide-experiences/${slug}.json`), 'utf8')).players || [];
          assert.ok(s.links.includes(`${slug}-guide.html`), `${game}: guide link`);
          assert.match(s.records, new RegExp(`公開されている実プレイ記録：${players.length}件`), `${game}: record count`);
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true, `${game}: horizontal overflow (${label})`);
        checks++;
      }
      // 2. games with a verified offer: notice stays hidden
      for (const game of withOffer.slice(0, 4)) {
        await open(game);
        const s = await state();
        assert.equal(s.boxVisible, false, `${game}: notice must be hidden`);
        assert.match(s.description, /\d+件の掲載枠/, `${game}: description counts verified offers`);
        checks++;
      }
    }

    // 3. offers appear: a verified row is added for a game that had none -> notice disappears
    const sample = body.find(r => r[col('verified')].toLowerCase() === 'true');
    const target = noOffer[0];
    const added = sample.slice();
    added[col('game')] = target;
    added[col('offerKey')] = `${target}|${added[col('site')]}|${added[col('platform')]}|${added[col('url')]}`;
    await open(target, toCsv([header, ...body, added]));
    let s = await state();
    assert.equal(s.boxVisible, false, 'notice must disappear once a verified offer exists');
    assert.notEqual(s.best, '検証済みの案件は未掲載');
    assert.match(s.description, /1件の掲載枠/);
    checks++;

    // 4. offers disappear: all rows of a game are removed -> notice appears, nothing claims absence
    const victim = withOffer[0];
    await open(victim, toCsv([header, ...body.filter(r => r[col('game')] !== victim)]));
    s = await state();
    assert.equal(s.boxVisible, true, 'notice must appear once the last verified offer is gone');
    assert.match(s.lead, /案件が存在しないとは断定していません/);
    assert.doesNotMatch(s.text, /確認できる案件なし|現在掲載なし/);
    checks++;

    // 5. an unreadable CSV must never be presented as "no offer exists"
    await page.unroute('**/data/published_offers.csv').catch(() => {});
    await page.route('**/data/published_offers.csv', route => route.fulfill({ status: 500, body: 'error' }));
    await page.goto(`${origin}/game.html?game=${encodeURIComponent(victim)}`, { waitUntil: 'networkidle' });
    s = await state();
    assert.doesNotMatch(s.text, /確認できる案件なし|現在掲載なし/);
    checks++;

    // 6. unknown game stays noindex + not-found
    await page.unroute('**/data/published_offers.csv').catch(() => {});
    await page.goto(`${origin}/game.html?game=__no_such_game__`, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('meta[name="robots"]').getAttribute('content'), 'noindex');
    checks++;

    const unexpected = errors.filter(m => !/published_offers\.csv|HTTP 500|Failed to fetch|NetworkError/.test(m));
    assert.deepEqual(unexpected, []);
    console.log(JSON.stringify({ gamesWithoutVerifiedOffer: noOffer.length, gamesWithOffer: withOffer.length, checks, pageErrors: unexpected.length }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(() => server.close());
