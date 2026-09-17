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
  const published = [
    'offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified',
    'active,Game,warau,,1000,active condition,iOS,通常,30日,2026-09-17,https://www.warau.jp/x,https://www.warau.jp/x,true',
    'archive,Game,chobirich,,31030,archived condition,Android,StepUp,60日,2026-09-08,https://www.chobirich.com/ad_details/1,https://www.chobirich.com/ad_details/1,false'
  ].join('\n');
  const policy = {
    games: { Game: { enabled: true } },
    publication: {
      allowLegacyFallback: false,
      currentPriceSources: ['warau']
    }
  };

  const api = makeContext(async (path) => {
    if (path.includes('refresh_policy')) {
      return { ok: true, status: 200, json: async () => policy };
    }
    if (path.includes('published')) {
      return { ok: true, status: 200, text: async () => published };
    }
    throw new Error(`unexpected fetch: ${path}`);
  });

  const loaded = await api.loadOffersWithFallback();
  assert.strictEqual(loaded.publishedCount, 1);
  assert.strictEqual(loaded.offers.length, 1);
  assert.strictEqual(loaded.offers[0].site, 'warau');
  assert.strictEqual(loaded.offers.some((offer) => offer.site === 'chobirich'), false);
  console.log('archived offer visibility tests passed');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
