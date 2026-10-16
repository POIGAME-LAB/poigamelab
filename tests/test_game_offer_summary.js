const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('site-data.js', 'utf8');
const context = { console, URL, fetch: async () => { throw new Error('unused'); }, window: { location: { href: 'https://example.test/' } } };
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context);
const api = context.window.POIGAME_DATA;
const label = (site) => ({ warau: 'ワラウ', moppy: 'モッピー' }[site] || site);

const offer = (o) => Object.assign({ site: 'warau', reward: 0, condition: '', platform: [], verified: true, updatedAt: '' }, o);

// verified offers: counts, range, best, per-OS best, latest date; reference rows are not mixed in
let r = api.summarizeGameOffers([
  offer({ reward: 21670, platform: ['Android'], condition: 'レベル70到達', updatedAt: '2026-10-01' }),
  offer({ reward: 16760, platform: ['iOS'], condition: 'レベル70到達', updatedAt: '2026-09-10' }),
  offer({ site: 'moppy', reward: 18100, platform: ['iOS'], updatedAt: '2026-10-03' }),
  offer({ site: 'coincome', reward: 99999, verified: false })
], label);
assert.strictEqual(r.verifiedCount, 3);
assert.strictEqual(r.referenceCount, 1);
assert.ok(r.lines[0].includes('3件') && r.lines[0].includes('ワラウ・モッピー') && r.lines[0].includes('2サイト'), r.lines[0]);
assert.strictEqual(r.lines[1], '還元額は16,760円〜21,670円です。');
assert.strictEqual(r.lines[2], '最高額の案件：ワラウ・Android／レベル70到達。');
assert.ok(!r.lines.join('').includes('99,999'), 'reference reward must not enter a verified summary');
assert.ok(r.lines.some((l) => l.includes('iOS 18,100円／Android 21,670円')), JSON.stringify(r.lines));
assert.ok(r.lines.some((l) => l.includes('2026-10-03')));

// single verified value, unknown OS: no OS line, no invented platform
r = api.summarizeGameOffers([offer({ reward: 5000, platform: ['不明'] })], label);
assert.strictEqual(r.lines[1], '還元額は5,000円です。');
assert.ok(!r.lines[2].includes('不明'));
assert.ok(!r.lines.some((l) => l.startsWith('OS別')));

// reference-only: clearly labelled as unverified, never presented as verified
r = api.summarizeGameOffers([offer({ reward: 600, verified: false })], label);
assert.strictEqual(r.verifiedCount, 0);
assert.ok(r.lines[0].includes('検証済みの案件データはまだありません'));
assert.ok(r.lines[1].includes('参考値として1件') && r.lines[1].includes('確認は完了していません'));

// no data / bad input: neutral wording, no "案件なし" claim, no crash
for (const input of [[], null, undefined, [offer({ reward: 0 })], [null]]) {
  r = api.summarizeGameOffers(input, label);
  assert.strictEqual(JSON.stringify(r.lines), JSON.stringify(['確認済みの案件データはまだありません。']));
}

// no label function supplied
r = api.summarizeGameOffers([offer({ reward: 100 })]);
assert.ok(r.lines[0].includes('warau'));

console.log('game offer summary tests: PASS');
