(() => {
  "use strict";

  // ---------------------------------------------------------------------
  // Shared display states. Every page uses the same five meanings and the
  // same wording, so "loading", "nothing verified", "download failed" and
  // "old data" can never be mistaken for one another.
  // ---------------------------------------------------------------------
  const LOAD_STATE = Object.freeze({
    LOADING: "loading",
    OK: "ok",
    EMPTY: "empty",
    FAILED: "failed",
    STALE: "stale"
  });

  const LOAD_STATE_TEXT = Object.freeze({
    loading: "読み込み中…",
    empty: "現在、確認済み案件の掲載はありません",
    failed: "最新情報を取得できませんでした",
    stale: "最終確認データを掲載中"
  });

  // An offer row's `updatedAt` is the JST date on which the point-site page
  // was last confirmed by POIGAME LAB (it advances on every successful
  // re-check, not only when the amount changes).
  const OFFER_FRESH_DAYS = 7;
  const OFFER_OLD_DAYS = 30;

  function jstDateString(now = Date.now()) {
    const date = new Date(Number(now) + 9 * 3600000);
    return date.toISOString().slice(0, 10);
  }

  function offerAgeDays(updatedAt, now = Date.now()) {
    const match = String(updatedAt || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    const confirmed = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    const today = Date.parse(`${jstDateString(now)}T00:00:00Z`);
    if (!Number.isFinite(confirmed) || !Number.isFinite(today)) return null;
    return Math.max(0, Math.round((today - confirmed) / 86400000));
  }

  function shortDate(updatedAt) {
    const match = String(updatedAt || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return match ? `${Number(match[2])}/${Number(match[3])}` : "";
  }

  function getOfferFreshness(offer, now = Date.now()) {
    if (!offer || !offer.verified) {
      return { level: "reference", days: null, date: "", text: "参考値（一次情報は未確認）", short: "参考値" };
    }
    const days = offerAgeDays(offer.updatedAt, now);
    const date = shortDate(offer.updatedAt);
    if (days === null) {
      return { level: "unknown", days: null, date: "", text: "確認日の記録なし", short: "確認日不明" };
    }
    const ago = days === 0 ? "本日" : `${days}日前`;
    if (days <= OFFER_FRESH_DAYS) {
      return { level: "fresh", days, date, text: `✓ ${date} 確認（${ago}）`, short: `${date}確認` };
    }
    if (days <= OFFER_OLD_DAYS) {
      return { level: "aging", days, date, text: `${date} 確認（${ago}）`, short: `${date}確認・${ago}` };
    }
    return {
      level: "old",
      days,
      date,
      text: `最終確認 ${date}（${ago}）・現在の掲載は未確認`,
      short: `${date}確認・${ago}`
    };
  }

  // Row label. Unlike getOfferHealthLabel it never answers with an
  // open-ended "確認中": it always states the confirmation date. Whether the
  // automatic check itself is late ("最終確認データを掲載中") is shown once per
  // page by the caller, not repeated on every row.
  function getOfferStatusLabel(offer, gameHealth, now = Date.now()) {
    const freshness = getOfferFreshness(offer, now);
    if (freshness.level === "reference") return { state: "legacy", ...freshness };
    return { state: freshness.level, ...freshness };
  }

  // The amount a page leads with. Verified rows confirmed within the last
  // OFFER_OLD_DAYS days win; an older verified row is used only when nothing
  // recent exists (callers show its age), and an unverified reference value
  // only when there is no verified row at all.
  function pickHeadlineOffer(offers, now = Date.now()) {
    const list = (Array.isArray(offers) ? offers : []).filter((offer) => offer && Number(offer.reward) > 0);
    const best = (rows) => rows.reduce(
      (top, offer) => (!top || Number(offer.reward) > Number(top.reward) ? offer : top), null);
    const verified = list.filter((offer) => offer.verified);
    const recent = verified.filter((offer) => {
      const days = offerAgeDays(offer.updatedAt, now);
      return days !== null && days <= OFFER_OLD_DAYS;
    });
    return best(recent) || best(verified) || best(list);
  }

  function summarizeCatalogOffers(offers, now = Date.now()) {
    const verified = (Array.isArray(offers) ? offers : [])
      .filter((offer) => offer && offer.verified && Number(offer.reward) > 0);
    const byReward = (list) => list.reduce(
      (top, offer) => (!top || Number(offer.reward) > Number(top.reward) ? offer : top), null);
    const recent = verified.filter((offer) => {
      const days = offerAgeDays(offer.updatedAt, now);
      return days !== null && days <= OFFER_OLD_DAYS;
    });
    const dates = verified.map((offer) => String(offer.updatedAt || "").trim())
      .filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value)).sort();
    return {
      verifiedCount: verified.length,
      recentCount: recent.length,
      oldCount: verified.length - recent.length,
      gameCount: new Set(verified.map((offer) => offer.gameName)).size,
      siteCount: new Set(verified.map((offer) => offer.site)).size,
      best: byReward(verified),
      bestRecent: byReward(recent),
      latestConfirmedAt: dates.length ? dates[dates.length - 1] : "",
      recentDays: OFFER_OLD_DAYS
    };
  }

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

  function formatOfferSourceLabel(siteName, provider) {
    const site = String(siteName || "").trim();
    const network = String(provider || "").trim();
    if (!network) return site;
    if (!site) return network;
    return `${site} × ${network}`;
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

  // 2026-11-24 operator decision: a verified amount that the daily check has not re-confirmed
  // for more than 7 days is not shown (the row stays in the CSV; nothing is deleted).
  const DEFAULT_MAX_OFFER_AGE_DAYS = 7;

  function jstDayNumber(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || "").trim());
    if (!match) return null;
    return Math.floor(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) / 86400000);
  }

  // Signed age used only for the 7-day rule: a future-dated row gives a negative age and is not trusted.
  // (offerAgeDays above is the display helper; it never goes below 0, which would make a future date look "today".)
  function signedOfferAgeDays(updatedAt, now = Date.now()) {
    const day = jstDayNumber(updatedAt);
    if (day === null) return null;
    const today = Math.floor((Number(now) + 9 * 3600000) / 86400000);
    return today - day;
  }

  function maxOfferAgeDays(policy) {
    const value = Number(policy?.publication?.maxOfferAgeDays);
    return Number.isFinite(value) && value >= 0 ? value : DEFAULT_MAX_OFFER_AGE_DAYS;
  }

  function isOfferFresh(offer, maxDays = DEFAULT_MAX_OFFER_AGE_DAYS, now = Date.now()) {
    const age = signedOfferAgeDays(offer?.updatedAt, now);
    return age !== null && age >= 0 && age <= maxDays;
  }

  function splitFreshOffers(rows, maxDays, now = Date.now()) {
    const fresh = [];
    const stale = [];
    (rows || []).forEach((offer) => (isOfferFresh(offer, maxDays, now) ? fresh : stale).push(offer));
    return {
      fresh,
      staleCount: stale.length,
      staleHiddenGames: [...new Set(stale.map((offer) => offer.gameName))]
        .filter((game) => !fresh.some((offer) => offer.gameName === game))
    };
  }

  async function loadOffersWithFallback(now = Date.now()) {
    let allPublishedRows = [];
    // A failed download is NOT the same thing as "no verified offers". Callers
    // read `status` so a fetch error is never rendered as an empty catalogue.
    let publishedLoadFailed = false;
    try {
      allPublishedRows = (await fetchCsv("data/published_offers.csv"))
        .map((row) => normalizeOffer(row, "published"))
        .filter((offer) => offer.gameName && offer.verified && offer.reward > 0);
    } catch (error) {
      publishedLoadFailed = true;
      console.warn("検証済み案件データを取得できませんでした。", error.message);
    }

    let managedGames;
    let policy;
    try {
      policy = await fetchJson("config/refresh_policy.json");
      managedGames = new Set(Object.keys(policy?.games || {}));
    } catch (error) {
      policy = null;
      console.info("更新ポリシーを確認できないため、旧案件データは表示しません。", error.message);
    }

    // Rows past the 7-day rule are hidden, not deleted. They are counted so the page can say so,
    // and a hidden row is never "re-filled" from the legacy file below.
    const freshness = splitFreshOffers(allPublishedRows, maxOfferAgeDays(policy), now);
    const publishedRows = freshness.fresh;
    const freshnessInfo = {
      maxOfferAgeDays: maxOfferAgeDays(policy),
      staleHiddenCount: freshness.staleCount,
      staleHiddenGames: freshness.staleHiddenGames
    };
    const withStatus = (result) => ({
      ...result,
      ...freshnessInfo,
      publishedLoadFailed,
      status: publishedLoadFailed
        ? LOAD_STATE.FAILED
        : (result.publishedCount > 0 ? LOAD_STATE.OK : LOAD_STATE.EMPTY)
    });

    if (!policy || policy?.publication?.allowLegacyFallback !== true) {
      return withStatus({
        offers: publishedRows,
        publishedCount: publishedRows.length,
        legacyCount: 0,
        usingPublished: publishedRows.length > 0
      });
    }

    let legacyRows = [];
    try {
      legacyRows = (await fetchCsv("offers.csv"))
        .map((row) => normalizeOffer(row, "legacy"))
        .filter((offer) => offer.gameName && offer.reward > 0);
    } catch (error) {
      console.error("旧案件データの読み込みに失敗しました", error);
    }

    const verifiedGames = new Set([...publishedRows.map((offer) => offer.gameName), ...freshness.staleHiddenGames]);
    const legacyOnly = legacyRows.filter((offer) =>
      !managedGames.has(offer.gameName) && !verifiedGames.has(offer.gameName)
    );

    return withStatus({
      offers: [...publishedRows, ...legacyOnly],
      publishedCount: publishedRows.length,
      legacyCount: legacyOnly.length,
      usingPublished: publishedRows.length > 0
    });
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
    // 2026-11-24 operator decision: an amount confirmed on one first-party site is shown as
    // confirmed (with its date). Having fewer than two comparison sites is not a warning.
    const reasons = Array.isArray(gameHealth.degradedReasons) ? gameHealth.degradedReasons : [];
    const onlyFewSources = reasons.length > 0 && reasons.every((reason) => reason === "comparison_sources_below_minimum");
    if (gameHealth.state === "degraded" && !onlyFewSources) {
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

  async function loadOfferHistory() {
    try {
      return (await fetchCsv("data/offer_history.csv"))
        .map((row) => ({
          observedAt: String(row.observedAt || "").trim(),
          game: String(row.game || "").trim(),
          site: String(row.site || "").trim(),
          platform: String(row.platform || "").trim() || "不明",
          reward: Number(row.reward) || 0,
          offerKey: String(row.offerKey || "").trim()
        }))
        .filter((row) => row.observedAt && row.game && row.site && row.reward > 0);
    } catch (error) {
      console.info("還元履歴はまだ利用できません。", error.message);
      return [];
    }
  }

  function buildRewardTrends(historyRows, currentOffers, gameName) {
    const historyByGroup = new Map();
    (historyRows || []).forEach((row) => {
      if (row.game !== gameName) return;
      const key = [row.site, row.platform || "不明"].join("|");
      if (!historyByGroup.has(key)) historyByGroup.set(key, []);
      historyByGroup.get(key).push(row);
    });
    historyByGroup.forEach((rows) => {
      rows.sort((a, b) => Date.parse(a.observedAt) - Date.parse(b.observedAt));
    });

    const currentByGroup = new Map();
    (currentOffers || []).forEach((offer) => {
      const platforms = Array.isArray(offer.platform) && offer.platform.length
        ? offer.platform
        : ["不明"];
      platforms.forEach((platform) => {
        const key = [offer.site, platform].join("|");
        const current = currentByGroup.get(key);
        if (!current || Number(offer.reward) > Number(current.reward)) {
          currentByGroup.set(key, { ...offer, trendPlatform: platform });
        }
      });
    });

    return [...currentByGroup.entries()].map(([key, offer]) => {
      const rows = historyByGroup.get(key) || [];
      const currentReward = Number(offer.reward) || 0;
      const changes = [];
      rows.forEach((row) => {
        const reward = Number(row.reward) || 0;
        const last = changes[changes.length - 1];
        if (!last || last.reward !== reward) {
          changes.push({ observedAt: row.observedAt, reward });
        }
      });
      const last = changes[changes.length - 1];
      if (!last || last.reward !== currentReward) {
        changes.push({
          observedAt: offer.updatedAt ? `${offer.updatedAt}T00:00:00Z` : new Date().toISOString(),
          reward: currentReward
        });
      }

      let previousReward = null;
      for (let i = changes.length - 2; i >= 0; i -= 1) {
        if (changes[i].reward !== currentReward) {
          previousReward = changes[i].reward;
          break;
        }
      }

      const priorChanges = changes.slice(0, -1);
      const previousHigh = priorChanges.length
        ? Math.max(...priorChanges.map((item) => item.reward))
        : null;
      const historicalHigh = Math.max(currentReward, previousHigh || 0);
      const changeAmount = previousReward === null ? null : currentReward - previousReward;
      const changePercent = previousReward
        ? ((currentReward - previousReward) / previousReward) * 100
        : null;
      const fromPreviousHighPercent = previousHigh
        ? ((currentReward - previousHigh) / previousHigh) * 100
        : null;

      return {
        site: offer.site,
        platform: offer.trendPlatform,
        currentReward,
        previousReward,
        changeAmount,
        changePercent,
        previousHigh,
        historicalHigh,
        fromPreviousHighPercent,
        changes: changes.slice(-6)
      };
    }).sort((a, b) => b.currentReward - a.currentReward);
  }

  function buildGameRewardTrend(historyRows, currentOffers, gameName, platform = "all") {
    const matchesPlatform = (value) => {
      const normalized = String(value || "").trim() || "不明";
      if (platform === "all") return true;
      if (platform === "unknown") return normalized === "不明";
      return normalized === platform;
    };

    const observedTimes = [...new Set(
      (historyRows || []).map((row) => row.observedAt).filter(Boolean)
    )].sort((a, b) => Date.parse(a) - Date.parse(b));

    const changes = [];
    let started = false;
    observedTimes.forEach((observedAt) => {
      const rewards = (historyRows || [])
        .filter((row) =>
          row.observedAt === observedAt
          && row.game === gameName
          && matchesPlatform(row.platform)
        )
        .map((row) => Number(row.reward) || 0)
        .filter((reward) => reward > 0);
      const reward = rewards.length ? Math.max(...rewards) : 0;
      if (!started && reward <= 0) return;
      started = true;
      const last = changes[changes.length - 1];
      if (!last || last.reward !== reward) {
        changes.push({ observedAt, reward });
      }
    });

    const currentRewards = [];
    (currentOffers || []).forEach((offer) => {
      const platforms = Array.isArray(offer.platform) && offer.platform.length
        ? offer.platform
        : ["不明"];
      if (platform === "all") {
        currentRewards.push(Number(offer.reward) || 0);
      } else if (platform === "unknown") {
        if (platforms.includes("不明")) currentRewards.push(Number(offer.reward) || 0);
      } else if (platforms.includes(platform)) {
        currentRewards.push(Number(offer.reward) || 0);
      }
    });
    const currentReward = currentRewards.length ? Math.max(...currentRewards) : 0;

    const last = changes[changes.length - 1];
    if (started && (!last || last.reward !== currentReward)) {
      changes.push({ observedAt: new Date().toISOString(), reward: currentReward });
    } else if (!started && currentReward > 0) {
      changes.push({ observedAt: new Date().toISOString(), reward: currentReward });
    }

    // A 0 entry only means no offer was listed for a while. When an offer is
    // back, compare with the last listed amount before that gap instead.
    let previousReward = null;
    let skippedGap = false;
    for (let i = changes.length - 2; i >= 0; i -= 1) {
      const reward = changes[i].reward;
      if (currentReward > 0 && reward <= 0) {
        skippedGap = true;
        continue;
      }
      if (skippedGap || reward !== currentReward) {
        previousReward = reward;
        break;
      }
    }

    const priorChanges = changes.slice(0, -1).filter((item) => item.reward > 0);
    const previousHigh = priorChanges.length
      ? Math.max(...priorChanges.map((item) => item.reward))
      : null;
    const changeAmount = previousReward === null ? null : currentReward - previousReward;
    const changePercent = previousReward
      ? ((currentReward - previousReward) / previousReward) * 100
      : null;
    const fromPreviousHighPercent = previousHigh
      ? ((currentReward - previousHigh) / previousHigh) * 100
      : null;

    return {
      platform,
      currentReward,
      available: currentReward > 0,
      previousReward,
      previousHigh,
      changeAmount,
      changePercent,
      fromPreviousHighPercent,
      changes: changes.slice(-6)
    };
  }

  function summarizeOfferCondition(condition, type = "") {
    const raw = String(condition || "").replace(/\s+/g, " ").trim();
    if (!raw) return "指定条件クリア";

    const furnaceMatches = [...raw.matchAll(/大溶鉱炉レベル(\d+)(?:に)?到達/g)].map((match) => Number(match[1]));
    if (furnaceMatches.length) {
      return `大溶鉱炉レベル${Math.max(...furnaceMatches)}到達`;
    }

    const goldenMatches = [...raw.matchAll(/黄金レベル(\d+)(?:に)?到達/g)].map((match) => Number(match[1]));
    if (goldenMatches.length) {
      return `黄金レベル${Math.max(...goldenMatches)}到達`;
    }

    const townHallMatches = [...raw.matchAll(/役場レベル(\d+)(?:に)?到達/g)].map((match) => Number(match[1]));
    if (townHallMatches.length) {
      return `役場レベル${Math.max(...townHallMatches)}到達`;
    }

    const levelMatches = [...raw.matchAll(/レベル(\d+)到達/g)].map((match) => Number(match[1]));
    if (levelMatches.length) {
      const maxLevel = Math.max(...levelMatches);
      const playerLabel = raw.includes(`プレイヤーレベル${maxLevel}到達`);
      return playerLabel ? `プレイヤーレベル${maxLevel}到達` : `レベル${maxLevel}到達`;
    }

    const ccMatch = raw.match(/(?:CC|コントロールセンター)(?:レベル)?([0-9/・]+)/i);
    if (ccMatch) {
      const levels = ccMatch[1].split(/[\/・]/).map(Number).filter(Number.isFinite);
      if (levels.length) return `コントロールセンターレベル${Math.max(...levels)}到達`;
    }

    const genericRankMatches = [];
    const genericRankPattern = /ランク(\d+)到達/g;
    let genericRankMatch;
    while ((genericRankMatch = genericRankPattern.exec(raw)) !== null) {
      const prefix = raw.slice(Math.max(0, genericRankMatch.index - 4), genericRankMatch.index);
      if (!prefix.endsWith("ユーザー")) {
        genericRankMatches.push(Number(genericRankMatch[1]));
      }
    }
    if (genericRankMatches.length) {
      return `ランク${Math.max(...genericRankMatches)}到達`;
    }

    const rankMatch = raw.match(/ユーザーランク([0-9/・]+)/);
    if (rankMatch) {
      const ranks = rankMatch[1].split(/[\/・]/).map(Number).filter(Number.isFinite);
      if (ranks.length) return `ユーザーランク${Math.max(...ranks)}到達`;
    }

    const consecutiveLogin = raw.match(/(\d+)日間連続(?:で)?ログインボーナス(?:を)?獲得/);
    if (consecutiveLogin) return `${consecutiveLogin[1]}日間連続ログインボーナス獲得`;

    const normalizedType = String(type || "").toLowerCase();
    if (normalizedType === "stepup" && raw.length > 40) {
      return "StepUpミッション最終Step達成";
    }

    return raw
      .replace(/^新規アプリインストール後[、,]\s*/, "")
      .replace(/^初回アプリインストール後[、,]\s*/, "")
      .replace(/^新規インストール後[、,]\s*/, "")
      .trim();
  }

  async function loadCoverageCandidates() {
    try {
      const payload = await fetchJson("data/comparison_candidate_queue.json");
      const safeEnvelope = payload?.candidateOnly === true
        && payload?.firstPartyVerificationRequired === true
        && payload?.publicationAuthorized === false;
      if (!safeEnvelope) {
        console.info("候補案件キューの安全フラグを確認できないため表示しません。");
        return { available: false, checkedAt: "", items: [] };
      }

      const rawItems = Array.isArray(payload.items) ? payload.items : [];
      const seen = new Set();
      const items = rawItems
        .filter((item) =>
          item?.candidateOnly === true
          && item?.firstPartyVerificationRequired === true
          && item?.publicationAuthorized === false
        )
        .map((item) => ({
          gameName: String(item.game || "").trim(),
          source: String(item.source || "").trim(),
          sourceLabel: String(item.sourceLabel || "").trim(),
          providerHint: String(item.providerHint || "").trim(),
          platformHint: String(item.platformHint || "").trim(),
          verificationState: String(item.verificationState || "").trim(),
          firstPartyCandidateUrl: safeHttpUrl(item.firstPartyCandidateUrl),
          checkedAt: String(item.checkedAt || payload.checkedAt || "").trim()
        }))
        .filter((item) => item.gameName && item.source)
        .filter((item) => {
          const key = [
            item.gameName,
            item.source,
            item.providerHint,
            item.platformHint,
            item.firstPartyCandidateUrl
          ].join("|");
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });

      return {
        available: true,
        checkedAt: String(payload.checkedAt || "").trim(),
        items
      };
    } catch (error) {
      console.info("候補案件キューはまだ利用できません。", error.message);
      return { available: false, checkedAt: "", items: [] };
    }
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

  function summarizeGameOffers(offers, labelOf, now = Date.now()) {
    const label = typeof labelOf === "function" ? labelOf : (site) => site;
    const yen = (value) => `${Number(value).toLocaleString("ja-JP")}円`;
    const usable = (Array.isArray(offers) ? offers : [])
      .filter((offer) => offer && Number(offer.reward) > 0);
    const verified = usable.filter((offer) => offer.verified);
    const reference = usable.filter((offer) => !offer.verified);
    const lines = [];

    if (verified.length > 0) {
      const rewards = verified.map((offer) => Number(offer.reward));
      const min = Math.min(...rewards);
      const max = Math.max(...rewards);
      const best = verified.reduce((top, offer) => (Number(offer.reward) > Number(top.reward) ? offer : top));
      const sites = [...new Set(verified.map((offer) => label(offer.site) || offer.site).filter(Boolean))];
      lines.push(`検証済みの案件を${verified.length}件掲載しています（${sites.join("・")}、${sites.length}サイト）。`);

      lines.push(min === max ? `還元額は${yen(max)}です。` : `還元額は${yen(min)}〜${yen(max)}です。`);

      const bestPlatforms = (best.platform || []).filter((item) => item && item !== "不明");
      let bestCondition = summarizeOfferCondition(best.condition, best.type);
      if (bestCondition.length > 40) bestCondition = `${bestCondition.slice(0, 39)}…`;
      const bestAge = offerAgeDays(best.updatedAt, now);
      const bestAgeNote = bestAge !== null && bestAge > OFFER_OLD_DAYS
        ? `（${shortDate(best.updatedAt)}確認・${bestAge}日前）`
        : "";
      lines.push(
        `最高額の案件：${label(best.site) || best.site}${bestPlatforms.length ? `・${bestPlatforms.join("・")}` : ""}／${bestCondition}${bestAgeNote}。`
      );

      // Per-OS amount follows the same 30-day rule as the headline; an older
      // row is only used when nothing recent exists, and then carries its date.
      const platformParts = ["iOS", "Android"].map((name) => {
        const pick = pickHeadlineOffer(verified.filter((offer) => (offer.platform || []).includes(name)), now);
        if (!pick) return "";
        const age = offerAgeDays(pick.updatedAt, now);
        return `${name} ${yen(pick.reward)}${age !== null && age > OFFER_OLD_DAYS ? `（${shortDate(pick.updatedAt)}確認）` : ""}`;
      }).filter(Boolean);
      if (platformParts.length) lines.push(`OS別の最高額：${platformParts.join("／")}（OSが明記された案件のみ）。`);

      const dates = verified.map((offer) => String(offer.updatedAt || "").trim()).filter(Boolean).sort();
      if (dates.length) lines.push(`最新の確認日：${dates[dates.length - 1]}。`);

      if (sites.length === 1) {
        lines.push(`現在、検証済みで掲載できているのは${sites[0]}のみです（他サイトの案件は確認できていません）。`);
      }
      const oldRows = verified.filter((offer) => {
        const days = offerAgeDays(offer.updatedAt, now);
        return days !== null && days > OFFER_OLD_DAYS;
      });
      if (oldRows.length) {
        lines.push(
          `${verified.length}件のうち${oldRows.length}件は、最終確認から${OFFER_OLD_DAYS}日以上たっています。金額や掲載の有無が変わっている可能性があるため、表の確認日を見て、申込み前に案件ページで確かめてください。`
        );
      }
    } else if (reference.length > 0) {
      const rewards = reference.map((offer) => Number(offer.reward));
      const min = Math.min(...rewards);
      const max = Math.max(...rewards);
      lines.push("検証済みの案件データはまだありません。");
      lines.push(
        `参考値として${reference.length}件（${min === max ? yen(max) : `${yen(min)}〜${yen(max)}`}）を表示していますが、一次情報での確認は完了していません。`
      );
    } else {
      lines.push("確認済みの案件データはまだありません。");
    }

    return {
      verifiedCount: verified.length,
      referenceCount: reference.length,
      lines
    };
  }

  window.POIGAME_DATA = {
    LOAD_STATE,
    LOAD_STATE_TEXT,
    OFFER_FRESH_DAYS,
    OFFER_OLD_DAYS,
    offerAgeDays,
    getOfferFreshness,
    getOfferStatusLabel,
    summarizeCatalogOffers,
    pickHeadlineOffer,
    parseCsv,
    rowsToObjects,
    fetchCsv,
    fetchJson,
    normalizePlatform,
    formatOfferSourceLabel,
    loadOffersWithFallback,
    isOfferFresh,
    splitFreshOffers,
    maxOfferAgeDays,
    hoursSince,
    buildGameHealth,
    loadDataHealth,
    getOfferHealthLabel,
    formatHealthUpdatedAt,
    loadOfferHistory,
    loadCoverageCandidates,
    buildRewardTrends,
    buildGameRewardTrend,
    summarizeOfferCondition,
    summarizeGameOffers,
    escapeHtml,
    safeHttpUrl
  };
})();
