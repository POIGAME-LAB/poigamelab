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
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return rowsToObjects(parseCsv(await response.text()));
  }

  async function fetchJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
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

  function hoursSince(iso, now = Date.now()) {
    const parsed = Date.parse(iso || "");
    if (!Number.isFinite(parsed)) return null;
    return Math.max(0, (now - parsed) / 3600000);
  }

  function buildGameHealth(refreshStatus, policy, now = Date.now()) {
    const staleAfterHours = Number(policy?.staleAfterHours || 48);
    const results = Array.isArray(refreshStatus?.results) ? refreshStatus.results : [];
    const finishedAt = refreshStatus?.finishedAt || refreshStatus?.startedAt || "";
    const ageHours = hoursSince(finishedAt, now);
    const output = {};

    results.forEach((item) => {
      const game = String(item?.game || "").trim();
      if (!game) return;
      const returncode = Number(item?.returncode ?? 1);
      const complete = item?.collectionComplete === true;
      const stale = ageHours !== null && ageHours > staleAfterHours;
      const failed = returncode !== 0;
      const degraded = !failed && !complete;
      let state = "fresh";
      if (failed) state = "failed";
      else if (degraded) state = "degraded";
      else if (stale) state = "stale";

      output[game] = {
        state,
        finishedAt,
        ageHours,
        staleAfterHours,
        collectionComplete: complete,
        publishableCount: Number(item?.publishableCount || 0),
        degradedReasons: Array.isArray(item?.degradedReasons) ? item.degradedReasons : []
      };
    });

    return output;
  }

  async function loadDataHealth() {
    try {
      const [refreshStatus, policy] = await Promise.all([
        fetchJson("data/refresh_status.json"),
        fetchJson("config/refresh_policy.json")
      ]);
      return {
        available: true,
        generatedAt: refreshStatus.finishedAt || refreshStatus.startedAt || "",
        success: refreshStatus.success === true,
        games: buildGameHealth(refreshStatus, policy),
        staleAfterHours: Number(policy?.staleAfterHours || 48)
      };
    } catch (error) {
      console.info("自動更新ステータスはまだ利用できません。", error.message);
      return { available: false, generatedAt: "", success: false, games: {}, staleAfterHours: 48 };
    }
  }

  function getOfferHealthLabel(offer, gameHealth) {
    if (!offer?.verified) return { state: "legacy", text: "参考掲載" };
    if (!gameHealth) {
      return {
        state: "verified",
        text: `✓ 掲載確認済み${offer.updatedAt ? ` ・ ${offer.updatedAt}更新` : ""}`
      };
    }

    if (gameHealth.state === "failed") {
      return { state: "warning", text: "掲載情報を確認中" };
    }
    if (gameHealth.state === "degraded") {
      return { state: "warning", text: "掲載情報を確認中" };
    }
    if (gameHealth.state === "stale") {
      return { state: "warning", text: "最終確認データを掲載中" };
    }
    return {
      state: "verified",
      text: `✓ 掲載確認済み${offer.updatedAt ? ` ・ ${offer.updatedAt}更新` : ""}`
    };
  }

  function formatHealthUpdatedAt(health) {
    if (!health?.generatedAt) return "確認待ち";
    const date = new Date(health.generatedAt);
    if (Number.isNaN(date.getTime())) return health.generatedAt;
    return new Intl.DateTimeFormat("ja-JP", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(date);
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
    fetchJson,
    normalizePlatform,
    loadOffersWithFallback,
    hoursSince,
    buildGameHealth,
    loadDataHealth,
    getOfferHealthLabel,
    formatHealthUpdatedAt,
    escapeHtml,
    safeHttpUrl
  };
})();
