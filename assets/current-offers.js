(() => {
  "use strict";
  const siteNames = {warau: "ワラウ", chobirich: "ちょびリッチ", moppy: "モッピー", hapitas: "ハピタス", pointtown: "ポイントタウン", coincome: "COINCOME", ecnavi: "ECナビ", amefuri: "アメフリ", gendama: "げん玉", point_income: "ポイントインカム"};
  const pages = {
    "township-lv60.html": "Township", "township-lv70.html": "Township",
    "kinoko-guide.html": "きのこ伝説", "mementomori-guide.html": "メメントモリ",
    "whiteout-survival-guide.html": "ホワイトアウト・サバイバル", "working-heroes-guide.html": "ワーキングヒーロー",
    "tokyo-debunker-guide.html": "東京ディバンカー", "puzzles-survival-guide.html": "パズル＆サバイバル",
    "kingshot-guide.html": "キングショット", "houchishojo-guide.html": "放置少女", "evertale-guide.html": "エバーテイル",
    "atlas-earth-guide.html": "ATLAS: EARTH", "family-farm-adventure-guide.html": "ファミリーファームの冒険",
    "klondike-adventures-guide.html": "クロンダイクの冒険", "merge-help-guide.html": "Merge Help: ホームデザインパズル",
    "magic-jigsaw-puzzles-guide.html": "マジックジグソーパズル"
  };
  const main = document.querySelector("main");
  const game = main?.getAttribute("data-current-offers-game") || pages[location.pathname.split("/").pop()];
  if (!main || !game || document.getElementById("current-verified-offers")) return;
  const section = document.createElement("section");
  section.id = "current-verified-offers";
  section.style.cssText = "margin:28px 0;padding:20px;border:1px solid #e9e3f7;border-radius:16px;background:#fff;overflow-wrap:anywhere";
  const heading = document.createElement("h2"); heading.textContent = "現在の確認済み案件";
  const note = document.createElement("p");
  note.textContent = "本文中の課金額・獲得記録は当時の実例です。以下は比較ページと同じ確認済みデータです。申込み前にリンク先の条件をご確認ください。";
  const list = document.createElement("div");
  section.append(heading, note, list); main.appendChild(section);
  const ready = window.POIGAME_DATA ? Promise.resolve() : new Promise((resolve, reject) => {
    const script = document.createElement("script"); script.src = "site-data.js";
    script.onload = resolve; script.onerror = reject; document.head.appendChild(script);
  });
  ready.then(() => window.POIGAME_DATA.loadOffersWithFallback()).then(result => {
    const rows = result.offers.filter(row => row.gameName === game && row.verified).sort((a, b) => b.reward - a.reward);
    if (!rows.length) { list.textContent = "現在、確認済みの案件データはありません。"; return; }
    rows.forEach(row => {
      const card = document.createElement("div"); card.style.cssText = "padding:14px 0;border-top:1px solid #eee;min-width:0";
      const title = document.createElement("strong");
      title.textContent = `${siteNames[row.site] || "ポイントサイト"} · ${row.reward.toLocaleString()}円 · ${row.platform} · 確認日 ${row.updatedAt || "未記載"}`;
      const details = document.createElement("details");
      const summary = document.createElement("summary"); summary.textContent = "達成条件・期限を見る";
      const conditions = document.createElement("p"); conditions.textContent = row.condition;
      const deadline = document.createElement("p"); deadline.textContent = row.deadline;
      details.append(summary, conditions, deadline);
      const link = document.createElement("a"); link.textContent = "ポイントサイトの案件を確認";
      link.href = window.POIGAME_DATA.safeHttpUrl(row.sourceUrl || row.url); link.rel = "noopener noreferrer";
      card.append(title, details, link); list.appendChild(card);
    });
  }).catch(() => { list.textContent = "案件データを読み込めませんでした。時間をおいてご確認ください。"; });
})();
