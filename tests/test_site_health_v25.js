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

  const requiredLaunchFiles = [
    'about.html',
    'privacy.html',
    'contact.html',
    'site-footer.js',
    'site-referrals.js',
    'robots.txt'
  ];
  requiredLaunchFiles.forEach((path) => assert.ok(fs.existsSync(path), `missing launch file: ${path}`));

  const publicPages = [
    'index.html',
    'game.html',
    'kinoko-guide.html',
    'mementomori-guide.html',
    'township-lv60.html',
    'township-lv70.html',
    'whiteout-survival-guide.html',
    'working-heroes-guide.html',
    'data-status.html',
    'about.html',
    'privacy.html',
    'contact.html'
  ];
  for (const path of publicPages) {
    const html = fs.readFileSync(path, 'utf8');
    assert.ok(html.includes('src="site-footer.js"'), `missing shared footer: ${path}`);
  }

  for (const path of publicPages) {
    const html = fs.readFileSync(path, 'utf8');
    assert.strictEqual(
      html.includes('\\n'),
      false,
      `literal \\n text leaked into public HTML: ${path}`
    );
  }

  const gamesCsvText = fs.readFileSync('games.csv', 'utf8');
  const gamesRows = api.rowsToObjects(api.parseCsv(gamesCsvText));
  const gamesByName = new Map(gamesRows.map(row => [row.name, row]));

  for (const gameName of ['Township', 'きのこ伝説']) {
    const game = gamesByName.get(gameName);
    assert.ok(game, `missing game row: ${gameName}`);
    assert.ok(game.overview && game.overview !== '調査中', `missing overview: ${gameName}`);
    assert.ok(game.days && game.days !== '調査中', `missing pace: ${gameName}`);
    assert.ok(game.difficulty && game.difficulty !== '調査中', `missing difficulty: ${gameName}`);
    assert.ok(game.tips && !game.tips.includes('準備中'), `missing tips: ${gameName}`);
  }

  const indexHtml = fs.readFileSync('index.html', 'utf8');
  assert.ok(indexHtml.includes('name="description"'));
  assert.ok(indexHtml.includes('ポイ活ゲーム案件比較・攻略 | POIGAME LAB'));
  assert.ok(indexHtml.includes('class="game-title-link"'));
  assert.strictEqual(indexHtml.includes('<div class="image-placeholder">GAME IMAGE</div>'), false);

  const gameHtml = fs.readFileSync('game.html', 'utf8');
  assert.ok(gameHtml.includes('id="rewardTrendList"'));
  assert.ok(gameHtml.includes('id="gameTrendSummary"'));
  assert.ok(gameHtml.includes('還元額の推移'));
  assert.ok(gameHtml.includes('過去最高'));
  assert.ok(gameHtml.includes('class="os-filter"'));
  assert.ok(gameHtml.includes('data-platform="iOS"'));
  assert.ok(gameHtml.includes('data-platform="Android"'));
  assert.ok(gameHtml.includes('id="offerCards"'));
  assert.ok(gameHtml.includes('class="section collapsible-section"'));
  assert.ok(gameHtml.includes('id="gameTips"'));
  assert.strictEqual(gameHtml.includes('攻略情報は準備中です。'), false);
  assert.ok(gameHtml.includes('mobile-offer-card'));
  assert.ok(gameHtml.includes('name="description"'));
  assert.ok(gameHtml.includes('現在確認できる案件はありません。'));

  const referralJs = fs.readFileSync('site-referrals.js', 'utf8');
  assert.ok(referralJs.includes('https://pc.moppy.jp/entry/invite.php?invite=Jh7He170'));
  assert.ok(referralJs.includes('code: "Jh7He170"'));
  assert.ok(referralJs.includes('https://www.warau.jp/friend/reg/d5em'));
  assert.ok(referralJs.includes('code: "d5eo"'));
  assert.strictEqual(referralJs.includes('hapitas'), false);

  for (const html of [indexHtml, gameHtml]) {
    assert.ok(html.includes('src="site-referrals.js"'));
    assert.ok(html.includes('［PR］'));
    assert.ok(html.includes('rel="sponsored noopener noreferrer"'));
  }
  assert.ok(gameHtml.includes('このサイトに登録［PR］'));
  assert.ok(gameHtml.includes('この案件を見る'));
  assert.ok(indexHtml.includes('このポイントサイトに登録［PR］'));
  assert.ok(indexHtml.includes('最高還元サイトへ'));

  const aboutHtml = fs.readFileSync('about.html', 'utf8');
  assert.ok(aboutHtml.includes('広告・アフィリエイト'));
  assert.ok(aboutHtml.includes('免責事項'));

  const privacyHtml = fs.readFileSync('privacy.html', 'utf8');
  assert.ok(privacyHtml.includes('Cookie'));
  assert.ok(privacyHtml.includes('個人情報'));

  const contactHtml = fs.readFileSync('contact.html', 'utf8');
  assert.ok(contactHtml.includes('https://github.com/POIGAME-LAB/poigamelab/issues/new'));
  assert.ok(contactHtml.includes('個人情報・秘密情報は投稿しないでください'));

  const referralJs = fs.readFileSync('site-referrals.js', 'utf8');
  assert.ok(referralJs.includes('https://pc.moppy.jp/entry/invite.php?invite=Jh7He170'));
  assert.ok(referralJs.includes('code: "Jh7He170"'));
  assert.ok(referralJs.includes('https://www.warau.jp/friend/reg/d5em'));
  assert.ok(referralJs.includes('code: "d5eo"'));
  assert.ok(referralJs.includes('https://hapitas.jp/appinvite?i=23001138&route=text'));
  assert.ok(referralJs.includes('code: "WSOVBE"'));

  const gameReferralHtml = fs.readFileSync('game.html', 'utf8');
  assert.ok(gameReferralHtml.includes('src="site-referrals.js"'));
  assert.ok(gameReferralHtml.includes('このサイトに登録［PR］'));
  assert.ok(gameReferralHtml.includes('rel="sponsored noopener noreferrer"'));
  assert.ok(gameReferralHtml.includes('この案件を見る'));

  const footerJs = fs.readFileSync('site-footer.js', 'utf8');
  for (const path of ['about.html', 'privacy.html', 'contact.html']) {
    assert.ok(footerJs.includes(path), `footer missing link: ${path}`);
  }

  const robots = fs.readFileSync('robots.txt', 'utf8');
  for (const path of ['/data/', '/config/', '/docs/', '/scripts/', '/tests/', '/data-status.html']) {
    assert.ok(robots.includes(`Disallow: ${path}`), `robots missing internal path: ${path}`);
  }

  const deployWorkflow = fs.readFileSync('.github/workflows/deploy-pages.yml', 'utf8');
  assert.ok(deployWorkflow.includes('workflow_dispatch:'));
  assert.ok(deployWorkflow.includes('push:'));
  assert.ok(deployWorkflow.includes('branches:'));
  assert.ok(deployWorkflow.includes('- main'));

  console.log('V25 site-health tests: PASS');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
