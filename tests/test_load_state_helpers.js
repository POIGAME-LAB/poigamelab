// Unit tests for the shared load-state / freshness helpers in site-data.js.
// Run: node tests/test_load_state_helpers.js
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('site-data.js', 'utf8');
function load(fetchImpl) {
  const context = { console: { ...console, info() {}, warn() {} }, URL, Intl, Date, fetch: fetchImpl,
    window: { location: { href: 'https://example.test/' } } };
  context.window.window = context.window;
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.window.POIGAME_DATA;
}

const NOW = Date.parse('2026-11-18T03:00:00Z'); // 2026-11-18 12:00 JST
const api = load(async () => { throw new Error('unused'); });

// Fixed vocabulary, one meaning each.
assert.strictEqual(api.LOAD_STATE_TEXT.loading, '読み込み中…');
assert.strictEqual(api.LOAD_STATE_TEXT.empty, '現在、確認済み案件の掲載はありません');
assert.strictEqual(api.LOAD_STATE_TEXT.failed, '最新情報を取得できませんでした');
assert.strictEqual(api.LOAD_STATE_TEXT.stale, '最終確認データを掲載中');
for (const text of Object.values(api.LOAD_STATE_TEXT)) assert.ok(!text.includes('確認中'), text);

// Age in JST calendar days.
assert.strictEqual(api.offerAgeDays('2026-11-18', NOW), 0);
assert.strictEqual(api.offerAgeDays('2026-11-16', NOW), 2);
assert.strictEqual(api.offerAgeDays('2026-09-28', NOW), 51);
assert.strictEqual(api.offerAgeDays('', NOW), null);
assert.strictEqual(api.offerAgeDays('not-a-date', NOW), null);
// 23:30 JST on 11-17 is still 11-17 in Japan even though UTC says 14:30.
assert.strictEqual(api.offerAgeDays('2026-11-17', Date.parse('2026-11-17T14:30:00Z')), 0);

const v = (reward, updatedAt, extra = {}) => ({ reward, updatedAt, verified: true, site: 'warau', platform: ['iOS'], gameName: 'G', ...extra });

// Freshness levels.
assert.strictEqual(api.getOfferFreshness(v(1, '2026-11-16'), NOW).level, 'fresh');
assert.strictEqual(api.getOfferFreshness(v(1, '2026-11-01'), NOW).level, 'aging');
const old = api.getOfferFreshness(v(1, '2026-09-28'), NOW);
assert.strictEqual(old.level, 'old');
assert.ok(old.text.includes('9/28') && old.text.includes('51日前') && old.text.includes('現在の掲載は未確認'), old.text);
assert.strictEqual(api.getOfferFreshness(v(1, ''), NOW).level, 'unknown');
assert.strictEqual(api.getOfferFreshness({ reward: 1, verified: false }, NOW).level, 'reference');

// Status label never answers with an open-ended "確認中".
for (const health of [undefined, { state: 'fresh' }, { state: 'degraded' }, { state: 'failed' }, { state: 'stale' }]) {
  const label = api.getOfferStatusLabel(v(1, '2026-11-16'), health, NOW);
  assert.ok(!label.text.includes('確認中'), label.text);
  assert.ok(label.text.includes('11/16'), label.text);
}
// the page-level stale notice is not repeated on each row
assert.strictEqual(api.getOfferStatusLabel(v(1, '2026-11-16'), { state: 'stale' }, NOW).state, 'fresh');
// the summary's "最高額の案件" line carries the age when that row is old
const ageLines = api.summarizeGameOffers([v(15230, '2026-11-16'), v(39740, '2026-09-28', { site: 'moppy' })], null, NOW).lines;
assert.ok(ageLines.some((l) => l.startsWith('最高額の案件') && l.includes('9/28確認・51日前')), JSON.stringify(ageLines));

// Headline: a recent verified row beats an older, higher one; reference only as last resort.
const recent = v(15230, '2026-11-16');
const higherOld = v(39740, '2026-09-28', { site: 'moppy' });
const reference = { reward: 99999, verified: false, updatedAt: '2026-11-16' };
assert.strictEqual(api.pickHeadlineOffer([higherOld, recent, reference], NOW), recent);
assert.strictEqual(api.pickHeadlineOffer([higherOld, reference], NOW), higherOld);
assert.strictEqual(api.pickHeadlineOffer([reference], NOW), reference);
assert.strictEqual(api.pickHeadlineOffer([], NOW), null);
assert.strictEqual(api.pickHeadlineOffer(null, NOW), null);

// Catalogue summary.
const summary = api.summarizeCatalogOffers([recent, higherOld, reference, v(500, '2026-11-10', { gameName: 'H', site: 'ec_navi' })], NOW);
assert.strictEqual(summary.verifiedCount, 3);
assert.strictEqual(summary.oldCount, 1);
assert.strictEqual(summary.gameCount, 2);
assert.strictEqual(summary.bestRecent, recent);
assert.strictEqual(summary.best, higherOld);
assert.strictEqual(summary.latestConfirmedAt, '2026-11-16');

// Game summary flags old rows and single-site comparisons.
const lines = api.summarizeGameOffers([recent, v(12650, '2026-11-16', { platform: ['Android'] })], null, NOW).lines;
assert.ok(lines.some((l) => l.includes('warauのみ')), JSON.stringify(lines));
const linesOld = api.summarizeGameOffers([recent, higherOld], null, NOW).lines;
assert.ok(linesOld.some((l) => l.includes('1件は、最終確認から30日以上')), JSON.stringify(linesOld));

(async () => {
  const header = 'offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified';
  const policy = { ok: true, status: 200, json: async () => ({ publication: { allowLegacyFallback: false } }) };
  const csv = (body) => ({ ok: true, status: 200, text: async () => body });

  // normal
  let r = await load(async (p) => p.includes('policy') ? policy
    : csv(`${header}\nk,G,warau,,100,x,iOS,通常,,2026-11-16,https://a.test/,https://a.test/,true\n`)).loadOffersWithFallback(NOW);
  assert.strictEqual(r.status, 'ok');
  assert.strictEqual(r.publishedLoadFailed, false);
  assert.strictEqual(r.staleHiddenCount, 0);
  // 7-day rule (operator decision 2026-11-24): a row not re-confirmed for more than 7 days is hidden, never a "failure".
  // It is counted, and the page reads "no verified offers" - not "could not be fetched".
  const stale = `${header}\nk,G,warau,,100,x,iOS,通常,,2026-11-01,https://a.test/,https://a.test/,true\n`;
  r = await load(async (p) => p.includes('policy') ? policy : csv(stale)).loadOffersWithFallback(NOW);
  assert.strictEqual(r.status, 'empty');
  assert.strictEqual(r.publishedLoadFailed, false);
  assert.strictEqual(r.offers.length, 0);
  assert.strictEqual(r.staleHiddenCount, 1);
  assert.strictEqual(JSON.stringify(r.staleHiddenGames), '["G"]');
  // a future-dated row is not trusted either (offerAgeDays alone would show it as "today")
  const future = `${header}\nk,G,warau,,100,x,iOS,通常,,2026-12-31,https://a.test/,https://a.test/,true\n`;
  r = await load(async (p) => p.includes('policy') ? policy : csv(future)).loadOffersWithFallback(NOW);
  assert.strictEqual(r.offers.length, 0);
  assert.strictEqual(r.status, 'empty');
  assert.strictEqual(api.offerAgeDays('2026-12-31', NOW), 0); // display helper stays non-negative
  // verified 0 rows: empty, not failed
  r = await load(async (p) => p.includes('policy') ? policy : csv(`${header}\n`)).loadOffersWithFallback(NOW);
  assert.strictEqual(r.status, 'empty');
  // download failure: failed, never empty
  r = await load(async (p) => p.includes('policy') ? policy : ({ ok: false, status: 500, text: async () => '' })).loadOffersWithFallback();
  assert.strictEqual(r.status, 'failed');
  assert.strictEqual(r.publishedLoadFailed, true);
  // network error + policy error
  r = await load(async () => { throw new Error('offline'); }).loadOffersWithFallback();
  assert.strictEqual(r.status, 'failed');

  console.log('load-state helper tests: PASS');
})().catch((error) => { console.error(error); process.exit(1); });
