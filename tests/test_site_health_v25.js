const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('site-data.js', 'utf8');

function makeContext(fetchImpl) {
  const context = {
    console,
    URL,
    Intl,
    Date,
    fetch: fetchImpl,
    window: { location: { href: 'https://example.test/index.html' } }
  };
  context.window.window = context.window;
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.window.POIGAME_DATA;
}

(async () => {
  const api = makeContext(async () => { throw new Error('unused'); });
  const now = Date.parse('2026-08-31T12:00:00Z');
  const base = {
    finishedAt: '2026-08-31T11:00:00Z',
    results: [
      { game: 'Township', returncode: 0, publishableCount: 5, collectionComplete: true, degradedReasons: [] },
      { game: 'きのこ伝説', returncode: 0, publishableCount: 6, collectionComplete: false, degradedReasons: ['known_page_failure'] },
      { game: '失敗ゲーム', returncode: 1, publishableCount: 2, collectionComplete: false, degradedReasons: [] }
    ]
  };
  const health = api.buildGameHealth(base, { staleAfterHours: 48 }, now);
  assert.strictEqual(health['Township'].state, 'fresh');
  assert.strictEqual(health['きのこ伝説'].state, 'degraded');
  assert.strictEqual(health['失敗ゲーム'].state, 'failed');

  const stale = api.buildGameHealth({
    finishedAt: '2026-08-28T00:00:00Z',
    results: [{ game: 'Township', returncode: 0, publishableCount: 5, collectionComplete: true }]
  }, { staleAfterHours: 48 }, now);
  assert.strictEqual(stale['Township'].state, 'stale');

  assert.strictEqual(api.getOfferHealthLabel({ verified: false }, health['Township']).state, 'legacy');
  assert.strictEqual(api.getOfferHealthLabel({ verified: true, updatedAt: '2026-08-31' }, health['Township']).state, 'verified');
  assert.strictEqual(api.getOfferHealthLabel({ verified: true }, health['きのこ伝説']).state, 'warning');
  assert.strictEqual(api.getOfferHealthLabel({ verified: true }, health['きのこ伝説']).text, '掲載情報を確認中');
  assert.strictEqual(api.getOfferHealthLabel({ verified: true }, health['失敗ゲーム']).state, 'warning');

  // A successful discovery run is not a verified offer refresh.
  const discovery = api.buildGameHealth({
    success: true,
    finishedAt: '2026-08-31T11:59:00Z',
    results: [{ game: 'Township', returncode: 0, publishableCount: 0,
      collectionComplete: false, standardConfirmed: 0, standardTotal: 6,
      degradedReasons: ['comparison_sources_below_minimum'] }]
  }, { staleAfterHours: 48 }, now);
  assert.strictEqual(discovery['Township'].state, 'degraded');
  const discoveryLabel = api.getOfferHealthLabel(
    { verified: true, updatedAt: '2026-08-29' }, discovery['Township']);
  assert.strictEqual(discoveryLabel.state, 'warning');
  assert.strictEqual(discoveryLabel.text, '掲載情報を確認中');

  const responses = {
    'data/refresh_status.json': {
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        finishedAt: '2026-08-31T11:00:00Z',
        results: [{ game: 'Township', returncode: 0, publishableCount: 5, collectionComplete: true, degradedReasons: [] }]
      })
    },
    'config/refresh_policy.json': {
      ok: true,
      status: 200,
      json: async () => ({ staleAfterHours: 36 })
    }
  };
  const apiFetch = makeContext(async (path) => responses[path]);
  const loaded = await apiFetch.loadDataHealth();
  assert.strictEqual(loaded.available, true);
  assert.strictEqual(loaded.staleAfterHours, 36);
  assert.strictEqual(loaded.games['Township'].collectionComplete, true);

  const apiUnavailable = makeContext(async () => ({ ok: false, status: 404, json: async () => ({}) }));
  const unavailable = await apiUnavailable.loadDataHealth();
  assert.strictEqual(unavailable.available, false);
  assert.deepStrictEqual(Object.keys(unavailable.games), []);

  console.log('V25 site-health tests: PASS');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
