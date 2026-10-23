// site-image-rights.js の POIGAME_CARD_IMAGE と、軽量版の読込失敗→原画像フォールバックの回帰テスト
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const listeners = {};
const sandbox = {
  window: { location: { pathname: '/offers.html' } },
  document: {
    readyState: 'complete',
    documentElement: { classList: { add() {} } },
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    querySelectorAll() { return []; },
    createElement() { return { style: {}, appendChild() {}, set textContent(v) {} }; },
    head: { appendChild() {} }
  },
  MutationObserver: class { observe() {} },
  Element: class {},
  HTMLImageElement: class {}
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('site-image-rights.js', 'utf8'), sandbox);
const helper = sandbox.window.POIGAME_CARD_IMAGE;
assert(helper, 'POIGAME_CARD_IMAGE is defined');

// 変換ルール（png/jpeg/二重拡張子/webp → assets/game-cards/*.webp）
const attrs = (v) => helper.attrs(v);
assert.strictEqual(attrs('assets/game-art/township-original.jpeg'),
  'src="assets/game-cards/township-original.webp" data-full-src="assets/game-art/township-original.jpeg"');
assert.strictEqual(attrs('assets/game-art/mementomori-new.png.PNG'),
  'src="assets/game-cards/mementomori-new.webp" data-full-src="assets/game-art/mementomori-new.png.PNG"');
assert.strictEqual(attrs('assets/game-art/New-Game.webp'),
  'src="assets/game-cards/new-game.webp" data-full-src="assets/game-art/New-Game.webp"');
// 対象外はそのまま（svg・外部URL・空）
assert.strictEqual(attrs('assets/game-art/whiteout-survival.svg'), 'src="assets/game-art/whiteout-survival.svg"');
assert.strictEqual(attrs('https://example.com/a.png'), 'src="https://example.com/a.png"');
assert.strictEqual(attrs(''), 'src=""');
// 属性エスケープ
assert(!attrs('x"><script>').includes('"><script>'));

// 404 → 原画像へ1回だけ戻し、後続の置換ハンドラへ伝播させない
const errorHandlers = listeners.error;
assert(errorHandlers && errorHandlers.length >= 1, 'error listener registered');
const img = Object.create(sandbox.HTMLImageElement.prototype);
img.dataset = { fullSrc: 'assets/game-art/township-original.jpeg' };
img.src = 'assets/game-cards/township-original.webp';
let stopped = 0;
const event = { target: img, stopImmediatePropagation() { stopped++; } };
errorHandlers[0](event);
assert.strictEqual(img.src, 'assets/game-art/township-original.jpeg');
assert.strictEqual(stopped, 1);
// 2回目の失敗では何もしない（既存のプレースホルダー処理に任せる）
errorHandlers[0](event);
assert.strictEqual(stopped, 1);
assert.strictEqual(img.src, 'assets/game-art/township-original.jpeg');

console.log('card image helper tests: PASS');
