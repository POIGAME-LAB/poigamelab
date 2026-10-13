#!/usr/bin/env node
// guides.html の #guideGrid に「JS実行前でも見える攻略ページへの<a>リンク」を書き出す。
// 元データ: games.csv / site-guides.js / site-researched-guides.js（guides.html のJS描画と同じ選び方・順序）。
// 使い方: node scripts/sync_static_guide_links.js          （書き込み）
//         node scripts/sync_static_guide_links.js --check  （差分があれば exit 1）
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const START = "<!-- POIGAME_STATIC_GUIDE_LINKS_START -->";
const END = "<!-- POIGAME_STATIC_GUIDE_LINKS_END -->";

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  text = text.replace(/^﻿/, "");
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((v) => v !== "")) rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); if (row.some((v) => v !== "")) rows.push(row); }
  const head = rows.shift() || [];
  return rows.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
}

function loadWindow(file) {
  const sandbox = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, file), "utf8"), sandbox);
  return sandbox.window;
}

function buildCards() {
  const guides = loadWindow("site-guides.js").POIGAME_GUIDES || {};
  const researched = loadWindow("site-researched-guides.js").POIGAME_RESEARCHED_GUIDES || {};
  const rows = parseCsv(fs.readFileSync(path.join(ROOT, "games.csv"), "utf8"));
  const seen = new Set();
  const cards = [];
  const add = (name, guide, inCatalog) => {
    if (!name || !guide || !Array.isArray(guide.links) || !guide.links.length || seen.has(name)) return;
    seen.add(name);
    const desc = String(guide.description || "").trim();
    cards.push(
      `    <article class="card"><div class="body">\n` +
      `      <h2>${esc(guide.title || name)}</h2>\n` +
      (desc ? `      <p>${esc(desc)}</p>\n` : "") +
      `      <div class="links">${guide.links.map((l) => `<a href="${esc(l.href)}">${esc(l.label)}</a>`).join("")}</div>\n` +
      (inCatalog ? `      <a class="compare" href="game.html?game=${encodeURIComponent(name)}#comparison">案件を比較する →</a>\n` : "") +
      `    </div></article>`
    );
  };
  rows.forEach((row) => {
    const name = String(row.name || "").trim();
    if (guides[name]) add(name, guides[name], true);
  });
  Object.entries(researched).forEach(([name, guide]) => add(name, guide, false));
  return cards;
}

function main() {
  const check = process.argv.includes("--check");
  const file = path.join(ROOT, "guides.html");
  const html = fs.readFileSync(file, "utf8");
  const a = html.indexOf(START), b = html.indexOf(END);
  if (a < 0 || b < a) { console.error("markers not found in guides.html"); process.exit(2); }
  const cards = buildCards();
  const block = `${START}\n${cards.join("\n")}\n    ${END}`;
  const next = html.slice(0, a) + block + html.slice(b + END.length);
  if (check) {
    if (next !== html) { console.error("guides.html の静的リンクが最新ではありません。node scripts/sync_static_guide_links.js を実行してください。"); process.exit(1); }
    console.log(`ok: ${cards.length} guides`);
    return;
  }
  if (next !== html) fs.writeFileSync(file, next);
  console.log(`${next !== html ? "updated" : "unchanged"}: ${cards.length} guides`);
}
main();
