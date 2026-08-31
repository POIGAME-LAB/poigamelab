(() => {
  "use strict";

  function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;

    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i];
      const next = text[i + 1];

      if (ch === '"') {
        if (quoted && next === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = !quoted;
        }
        continue;
      }

      if (ch === "," && !quoted) {
        row.push(field);
        field = "";
        continue;
      }

      if ((ch === "\n" || ch === "\r") && !quoted) {
        if (ch === "\r" && next === "\n") i += 1;
        row.push(field);
        field = "";
        if (row.some((value) => value !== "")) rows.push(row);
        row = [];
        continue;
      }

      field += ch;
    }

    if (field !== "" || row.length > 0) {
      row.push(field);
      if (row.some((value) => value !== "")) rows.push(row);
    }

    return rows;
  }

  function rowsToObjects(rows) {
    if (!rows.length) return [];
    const headers = rows[0].map((value) => value.trim());
    return rows.slice(1).map((row) => {
      const obj = {};
      headers.forEach((header, index) => {
        obj[header] = row[index] ?? "";
      });
      return obj;
    });
  }

  async function fetchCsv(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${path}: HTTP ${response.status}`);
    }
    return rowsToObjects(parseCsv(await response.text()));
  }

  function normalizePlatform(value) {
    const raw = String(value || "").trim();
    if (!raw || raw === "不明") return raw ? [raw] : [];
    return raw.split("|").map((item) => item.trim()).filter(Boolean);
  }

  function normalizeOffer(row, source) {
    return {
      offerKey: String(row.offerKey || "").trim(),
      gameName: String(row.game || "").trim(),
      site: String(row.site || "").trim(),
      provider: String(row.provider || "").trim(),
      reward: Number(row.reward) || 0,
      condition: String(row.condition || "").trim(),
      platform: normalizePlatform(row.platform),
      type: String(row.type || "").trim(),
      deadline: String(row.deadline || "").trim(),
      updatedAt: String(row.updatedAt || "").trim(),
      url: safeHttpUrl(row.url),
      sourceUrl: safeHttpUrl(row.sourceUrl),
      verified: String(row.verified || "").trim().toLowerCase() === "true",
      dataSource: source
    };
  }

  async function loadOffersWithFallback() {
    let publishedRows = [];
    try {
      publishedRows = (await fetchCsv("data/published_offers.csv"))
        .map((row) => normalizeOffer(row, "published"))
        .filter((offer) => offer.gameName && offer.verified && offer.reward > 0);
    } catch (error) {
      console.info("検証済み案件データはまだありません。旧データへフォールバックします。", error.message);
    }

    let legacyRows = [];
    try {
      legacyRows = (await fetchCsv("offers.csv"))
        .map((row) => normalizeOffer(row, "legacy"))
        .filter((offer) => offer.gameName && offer.reward > 0);
    } catch (error) {
      console.error("旧案件データの読み込みにも失敗しました", error);
    }

    const verifiedGames = new Set(publishedRows.map((offer) => offer.gameName));
    const legacyOnly = legacyRows.filter((offer) => !verifiedGames.has(offer.gameName));

    return {
      offers: [...publishedRows, ...legacyOnly],
      publishedCount: publishedRows.length,
      legacyCount: legacyOnly.length,
      usingPublished: publishedRows.length > 0
    };
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function safeHttpUrl(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    try {
      const url = new URL(raw, window.location.href);
      if (!/^https?:$/.test(url.protocol)) return "";
      return url.href;
    } catch (_error) {
      return "";
    }
  }

  window.POIGAME_DATA = {
    parseCsv,
    rowsToObjects,
    fetchCsv,
    normalizePlatform,
    loadOffersWithFallback,
    escapeHtml,
    safeHttpUrl
  };
})();
