// 2026-11-24 operator decision: verified amounts not re-confirmed for more than 7 days are hidden
// (never deleted), and a game hidden that way does not fall back to unverified catalog amounts.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('site-data.js', 'utf8');

function makeContext(files) {
  const context = {
    console: { info() {}, error() {}, log() {} },
    URL,
    Intl,
    Date,
    fetch: async (path) => {
      const key = String(path).split('?', 1)[0];
      if (!(key in files)) return { ok: false, status: 404, text: async () => '', json: async () => ({}) };
      const body = files[key];
      return { ok: true, status: 200, text: async () => body, json: async () => JSON.parse(body) };
    },
    window: { location: { href: 'https://example.test/index.html' } }
  };
  context.window.window = context.window;
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.window.POIGAME_DATA;
}

const header = 'offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified';
const row = (key, game, reward, updatedAt) =>
  `${key},${game},moppy,,${reward},条件,iOS,StepUp,期限,${updatedAt},https://pc.moppy.jp/ad/detail.php?site_id=1,https://pc.moppy.jp/ad/detail.php?site_id=1,true`;

(async () => {
  // 2026-11-24 10:00 JST
  const now = Date.parse('2026-11-24T01:00:00Z');
  const api = makeContext({});
  assert.strictEqual(api.offerAgeDays('2026-11-24', now), 0);
  assert.strictEqual(api.offerAgeDays('2026-11-17', now), 7);
  assert.strictEqual(api.offerAgeDays('', now), null);
  assert.strictEqual(api.isOfferFresh({ updatedAt: '2026-11-17' }, 7, now), true);
  assert.strictEqual(api.isOfferFresh({ updatedAt: '2026-11-16' }, 7, now), false);
  assert.strictEqual(api.isOfferFresh({ updatedAt: 'not-a-date' }, 7, now), false);
  assert.strictEqual(api.isOfferFresh({ updatedAt: '2026-11-30' }, 7, now), false); // future date is not trusted
  // JST day boundary: 2026-11-23 23:30 JST is still the 23rd
  assert.strictEqual(api.offerAgeDays('2026-11-23', Date.parse('2026-11-23T14:30:00Z')), 0);
  assert.strictEqual(api.maxOfferAgeDays({ publication: { maxOfferAgeDays: 3 } }), 3);
  assert.strictEqual(api.maxOfferAgeDays({}), 7);
  assert.strictEqual(api.maxOfferAgeDays(null), 7);

  const csv = [header,
    row('a', 'キングショット', 23367, '2026-09-28'),
    row('b', 'パズル＆サバイバル', 15230, '2026-11-23'),
    row('c', 'パズル＆サバイバル', 39740, '2026-09-28')].join('\n');
  const policy = JSON.stringify({ games: { 'キングショット': {}, 'パズル＆サバイバル': {} }, publication: { allowLegacyFallback: false } });
  const loaded = await makeContext({ 'data/published_offers.csv': csv, 'config/refresh_policy.json': policy })
    .loadOffersWithFallback(now);
  assert.strictEqual(JSON.stringify(loaded.offers.map((o) => o.offerKey)), '["b"]');
  assert.strictEqual(loaded.staleHiddenCount, 2);
  assert.strictEqual(JSON.stringify(loaded.staleHiddenGames), '["キングショット"]'); // パズサバ still has a fresh row
  assert.strictEqual(loaded.maxOfferAgeDays, 7);

  // Policy unavailable: the same 7-day rule still applies.
  const noPolicy = await makeContext({ 'data/published_offers.csv': csv }).loadOffersWithFallback(now);
  assert.strictEqual(JSON.stringify(noPolicy.offers.map((o) => o.offerKey)), '["b"]');

  // games.js must not replace hidden verified rows with catalog reference amounts.
  const gamesJs = fs.readFileSync('games.js', 'utf8');
  assert.ok(gamesJs.includes('result?.staleHiddenGames'), 'games.js must respect staleHiddenGames');

  console.log('offer freshness v1: ok');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
