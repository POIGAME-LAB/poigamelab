const pointSites = {
    moppy: "モッピー",
    warau: "ワラウ",
    chobirich: "ちょびリッチ",
    coincome: "COINCOME",
    mikoshi: "MIKOSHI",
    pointtown: "ポイントタウン",
    hapitas: "ハピタス",
    ecnav: "ECナビ",
    pointincome: "ポイントインカム",
    getmoney: "GetMoney!",
    itsmon: "itsmon",
    poney: "PONEY",
    rakuten: "楽天リーベイツ",
    mercari: "メルカリ"
  };

  const games = [];

  // Catalog provisional rewards are display-only hints until a verified
  // published offer exists. This keeps newly listed games useful on index/game
  // without pretending candidate research is first-party verified.
  (() => {
    let poigameDataValue;
    const sourceAliases = {
      "coincome": "coincome",
      "ワラウ": "warau",
      "warau": "warau",
      "モッピー": "moppy",
      "moppy": "moppy",
      "ハピタス": "hapitas",
      "hapitas": "hapitas"
    };

    Object.defineProperty(window, "POIGAME_DATA", {
      configurable: true,
      get() {
        return poigameDataValue;
      },
      set(value) {
        if (value && typeof value.loadOffersWithFallback === "function" && typeof value.fetchCsv === "function") {
          const originalLoadOffersWithFallback = value.loadOffersWithFallback.bind(value);
          value.loadOffersWithFallback = async function loadOffersWithCatalogProvisionalFallback() {
            const result = await originalLoadOffersWithFallback();
            const offers = Array.isArray(result?.offers) ? [...result.offers] : [];
            const gamesWithVerifiedOffer = new Set(
              offers.filter((offer) => offer?.verified).map((offer) => offer.gameName)
            );
            let provisionalCount = 0;

            try {
              const rows = await value.fetchCsv("games.csv");
              rows.forEach((row) => {
                const gameName = String(row.name || "").trim();
                const reward = Number(row.provisionalReward) || 0;
                if (!gameName || reward <= 0 || gamesWithVerifiedOffer.has(gameName)) return;

                const rawSource = String(row.provisionalSource || "").trim();
                const aliasKey = rawSource.toLowerCase();
                const site = sourceAliases[aliasKey] || sourceAliases[rawSource] || aliasKey || "調査中";
                offers.push({
                  offerKey: `catalog-provisional|${gameName}|${site}`,
                  gameName,
                  site,
                  provider: "公開情報調査",
                  reward,
                  condition: String(row.condition || "").trim() || "指定条件クリア",
                  platform: [],
                  type: "参考",
                  deadline: "",
                  updatedAt: String(row.addedDate || "").trim(),
                  url: "",
                  sourceUrl: "",
                  verified: false,
                  dataSource: "catalog-provisional"
                });
                provisionalCount += 1;
              });
            } catch (error) {
              console.info("新着ゲームの参考還元はまだ利用できません。", error.message);
            }

            return {
              ...result,
              offers,
              provisionalCount
            };
          };
        }
        poigameDataValue = value;
      }
    });
  })();
