const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('site-data.js', 'utf8');

function makeContext(fetchImpl) {
  const context = {
    console,
    URL,
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
  const parsed = api.rowsToObjects(api.parseCsv(
    'game,reward,condition\r\nTownship,16760,"累計条件, 30日以内"\r\n"きのこ伝説",22000,"引用 ""あり"""\r\n'
  ));
  assert.strictEqual(parsed.length, 2);
  assert.strictEqual(parsed[0].condition, '累計条件, 30日以内');
  assert.strictEqual(parsed[1].condition, '引用 "あり"');

  const published = [
    'offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified',
    'k1,Township,warau,,16760,"累計条件, 30日以内",iOS,StepUp,30日,2026-08-31,https://www.warau.jp/x,https://www.warau.jp/x,true',
  ].join('\n');
  const legacy = [
    'game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified',
    'Township,moppy,,8000,旧案件,iOS|Android,通常,,2026-08-29,https://moppy.jp/,https://moppy.jp/,false',
    'メメントモリ,coincome,,7200,旧案件,iOS|Android,通常,,2026-08-29,https://cimcome.jp/,https://cimcome.jp/,false',
    '未管理ゲーム,coincome,,555,旧参考案件,iOS,通常,,2026-08-29,https://cimcome.jp/,https://cimcome.jp/,false',
  ].join('\n');
  const policy = {
    games: {
      Township: { enabled: true },
      'メメントモリ': { enabled: true }
    },
    publication: { allowLegacyFallback: true }
  };

  const apiMerge = makeContext(async (path) => {
    if (path.includes('refresh_policy')) {
      return { ok: true, status: 200, json: async () => policy };
    }
    const text = path.includes('published') ? published : legacy;
    return { ok: true, status: 200, text: async () => text };
  });
  const merged = await apiMerge.loadOffersWithFallback();
  assert.strictEqual(merged.publishedCount, 1);
  assert.strictEqual(merged.legacyCount, 1);
  assert.strictEqual(merged.offers.length, 2);
  assert.strictEqual(merged.offers.find(x => x.gameName === 'Township').reward, 16760);
  assert.strictEqual(merged.offers.some(x => x.gameName === 'メメントモリ'), false);
  assert.strictEqual(merged.offers.find(x => x.gameName === '未管理ゲーム').verified, false);

  const apiFallback = makeContext(async (path) => {
    if (path.includes('refresh_policy')) {
      return { ok: true, status: 200, json: async () => policy };
    }
    if (path.includes('published')) return { ok: false, status: 404, text: async () => '' };
    return { ok: true, status: 200, text: async () => legacy };
  });
  const fallback = await apiFallback.loadOffersWithFallback();
  assert.strictEqual(fallback.publishedCount, 0);
  assert.strictEqual(fallback.legacyCount, 1);
  assert.strictEqual(fallback.offers.length, 1);
  assert.strictEqual(fallback.offers[0].gameName, '未管理ゲーム');

  const launchPolicy = {
    games: policy.games,
    publication: { allowLegacyFallback: false }
  };
  const launchRequests = [];
  const apiLaunch = makeContext(async (path) => {
    launchRequests.push(path);
    if (path.includes('refresh_policy')) {
      return { ok: true, status: 200, json: async () => launchPolicy };
    }
    if (path.includes('published')) {
      return { ok: true, status: 200, text: async () => published };
    }
    throw new Error(`launch must not request legacy offers: ${path}`);
  });
  const launch = await apiLaunch.loadOffersWithFallback();
  assert.strictEqual(launch.publishedCount, 1);
  assert.strictEqual(launch.legacyCount, 0);
  assert.strictEqual(launch.offers.length, 1);
  assert.strictEqual(launchRequests.some(path => path === 'offers.csv'), false);

  const apiPolicyFailClosed = makeContext(async (path) => {
    if (path.includes('refresh_policy')) {
      return { ok: false, status: 500, json: async () => ({}) };
    }
    const text = path.includes('published') ? published : legacy;
    return { ok: true, status: 200, text: async () => text };
  });
  const policyFailClosed = await apiPolicyFailClosed.loadOffersWithFallback();
  assert.strictEqual(policyFailClosed.publishedCount, 1);
  assert.strictEqual(policyFailClosed.legacyCount, 0);
  assert.strictEqual(policyFailClosed.offers.length, 1);

  assert.strictEqual(api.safeHttpUrl('javascript:alert(1)'), '');
  assert.ok(api.safeHttpUrl('https://example.com/path').startsWith('https://example.com/path'));
  assert.strictEqual(api.escapeHtml('<script>'), '&lt;script&gt;');

  const actualPolicy = JSON.parse(fs.readFileSync('config/refresh_policy.json', 'utf8'));
  assert.strictEqual(actualPolicy.publication.allowLegacyFallback, false);

  // The real revised CSV must survive the same reader used by game.html.
  const actualCsv = fs.readFileSync('data/published_offers.csv', 'utf8');
  const actualRows = api.rowsToObjects(api.parseCsv(actualCsv));
  const endedWarauIds = new Set(['205975', '206035', '205389', '205390']);
  assert.strictEqual(actualRows.some(row =>
    row.site === 'warau' && [...endedWarauIds].some(id => String(row.url || '').includes(`point_id=${id}`))
  ), false);

  const targets = JSON.parse(fs.readFileSync('config/game_targets.json', 'utf8')).games;
  for (const gameName of ['メメントモリ', 'ホワイトアウト・サバイバル']) {
    const target = targets.find(item => item.game === gameName);
    const warauUrls = ((target.known_urls_by_source || {}).warau || []);
    assert.strictEqual(warauUrls.some(url =>
      [...endedWarauIds].some(id => String(url).includes(`point_id=${id}`))
    ), false);
  }
  const candidateKeys = JSON.parse(fs.readFileSync('data/warau_baseline_candidates.json', 'utf8'))
    .candidates.map(candidate => candidate.offerKey);
  const selectedRows = actualRows.filter(row => candidateKeys.includes(row.offerKey));
  assert.strictEqual(selectedRows.length, 4);
  for (const row of selectedRows) {
    assert.ok(row.condition.length > 20);
    assert.ok(row.deadline.includes('インストール日から起算'));
    assert.ok(row.url.startsWith('https://www.warau.jp/'));
    if (row.game === 'きのこ伝説') {
      assert.ok(row.condition.includes('レベル100到達後に一括3200円課金'));
      assert.ok(row.condition.includes('45日以内：プレイヤーレベル125到達'));
    }
  }

  const trendHistory = [
    { observedAt: '2026-08-31T00:00:00Z', game: 'Township', site: 'coincome', platform: 'Android', reward: 30000 },
    { observedAt: '2026-09-01T00:00:00Z', game: 'Township', site: 'coincome', platform: 'Android', reward: 33125 },
    { observedAt: '2026-08-31T00:00:00Z', game: 'Township', site: 'warau', platform: 'Android', reward: 25000 },
    { observedAt: '2026-09-01T00:00:00Z', game: 'Township', site: 'warau', platform: 'Android', reward: 20000 },
  ];
  const trendOffers = [
    { gameName: 'Township', site: 'coincome', platform: ['Android'], reward: 33125, updatedAt: '2026-09-04' },
    { gameName: 'Township', site: 'warau', platform: ['Android'], reward: 20000, updatedAt: '2026-09-04' },
  ];
  const trends = api.buildRewardTrends(trendHistory, trendOffers, 'Township');
  const coincomeTrend = trends.find(item => item.site === 'coincome');
  const warauTrend = trends.find(item => item.site === 'warau');
  assert.strictEqual(coincomeTrend.currentReward, 33125);
  assert.strictEqual(coincomeTrend.previousReward, 30000);
  assert.strictEqual(coincomeTrend.changeAmount, 3125);
  assert.ok(Math.abs(coincomeTrend.changePercent - 10.4166667) < 0.001);
  assert.strictEqual(coincomeTrend.previousHigh, 30000);
  assert.strictEqual(coincomeTrend.historicalHigh, 33125);
  assert.ok(Math.abs(coincomeTrend.fromPreviousHighPercent - 10.4166667) < 0.001);
  assert.strictEqual(warauTrend.currentReward, 20000);
  assert.strictEqual(warauTrend.previousReward, 25000);
  assert.strictEqual(warauTrend.previousHigh, 25000);
  assert.strictEqual(warauTrend.historicalHigh, 25000);
  assert.strictEqual(warauTrend.changeAmount, -5000);
  assert.ok(Math.abs(warauTrend.fromPreviousHighPercent - (-20)) < 0.001);

  const gameTrendHistory = [
    { observedAt: '2026-09-01T00:00:00Z', game: 'Game X', site: 'warau', platform: 'Android', reward: 11500 },
    { observedAt: '2026-09-02T00:00:00Z', game: 'Game X', site: 'warau', platform: 'Android', reward: 12500 },
    { observedAt: '2026-09-03T00:00:00Z', game: 'Other Game', site: 'warau', platform: 'Android', reward: 5000 },
  ];
  const endedGameTrend = api.buildGameRewardTrend(gameTrendHistory, [], 'Game X', 'Android');
  assert.strictEqual(endedGameTrend.available, false);
  assert.strictEqual(endedGameTrend.currentReward, 0);
  assert.strictEqual(endedGameTrend.previousReward, 12500);
  assert.strictEqual(endedGameTrend.previousHigh, 12500);
  assert.strictEqual(endedGameTrend.changeAmount, -12500);
  assert.strictEqual(endedGameTrend.changePercent, -100);
  assert.strictEqual(endedGameTrend.fromPreviousHighPercent, -100);
  assert.deepStrictEqual(
    Array.from(endedGameTrend.changes).map(item => item.reward),
    [11500, 12500, 0]
  );

  const actualHistory = api.rowsToObjects(api.parseCsv(fs.readFileSync('data/offer_history.csv', 'utf8')));
  assert.ok(actualHistory.length > 0);
  assert.ok(actualHistory.some(row =>
    row.game === 'ホワイトアウト・サバイバル'
    && row.site === 'warau'
    && row.platform === 'Android'
    && row.reward === '12500'
  ));

  console.log('V24 site-data tests: PASS');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
