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
  ].join('\n');

  const apiMerge = makeContext(async (path) => {
    const text = path.includes('published') ? published : legacy;
    return { ok: true, status: 200, text: async () => text };
  });
  const merged = await apiMerge.loadOffersWithFallback();
  assert.strictEqual(merged.publishedCount, 1);
  assert.strictEqual(merged.legacyCount, 1);
  assert.strictEqual(merged.offers.length, 2);
  assert.strictEqual(merged.offers.find(x => x.gameName === 'Township').reward, 16760);
  assert.strictEqual(merged.offers.find(x => x.gameName === 'メメントモリ').verified, false);

  const apiFallback = makeContext(async (path) => {
    if (path.includes('published')) return { ok: false, status: 404, text: async () => '' };
    return { ok: true, status: 200, text: async () => legacy };
  });
  const fallback = await apiFallback.loadOffersWithFallback();
  assert.strictEqual(fallback.publishedCount, 0);
  assert.strictEqual(fallback.legacyCount, 2);

  assert.strictEqual(api.safeHttpUrl('javascript:alert(1)'), '');
  assert.ok(api.safeHttpUrl('https://example.com/path').startsWith('https://example.com/path'));
  assert.strictEqual(api.escapeHtml('<script>'), '&lt;script&gt;');

  const indexSource = fs.readFileSync('index.html', 'utf8');
  const gameSource = fs.readFileSync('game.html', 'utf8');
  assert.ok(indexSource.includes('POIGAME_DATA.isOfferFresh'));
  assert.ok(gameSource.includes('POIGAME_DATA.isOfferFresh'));
  assert.ok(gameSource.includes('row.classList.add("inactive-row")'));
  assert.ok(gameSource.includes('class="stale-note"'));

  // The real revised CSV must survive the same reader used by game.html.
  const actualCsv = fs.readFileSync('data/published_offers.csv', 'utf8');
  const actualRows = api.rowsToObjects(api.parseCsv(actualCsv));
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

  console.log('V24 site-data tests: PASS');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
