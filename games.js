const pointSites = {
    moppy: "モッピー",
    warau: "ワラウ",
    chobirich: "ちょびリッチ",
    coincome: "COINCOME",
    mikoshi: "MIKOSHI",
    gendama: "げん玉",
    kurashiru_reward: "クラシルリワード（レシチャレ）",
    amefuri: "アメフリ",
    point_town: "ポイントタウン",
    pointtown: "ポイントタウン",
    hapitas: "ハピタス",
    ec_navi: "ECナビ",
    ecnavi: "ECナビ",
    ecnav: "ECナビ",
    point_income: "ポイントインカム",
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

    const pathname = String(window.location.pathname || "");
    const isIndexPage = pathname === "/" || /\/index\.html$/.test(pathname);

    if (isIndexPage) {
      const styleHref = "assets/index-compact-v2.css?v=20260915-1815";
      if (!document.querySelector('link[data-poigame-compact-v2="1"]')) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = styleHref;
        link.dataset.poigameCompactV2 = "1";
        document.head.appendChild(link);
      }

      if (!document.querySelector('script[data-poigame-compact-v2="1"]')) {
        const script = document.createElement("script");
        script.src = "assets/index-compact-v2.js?v=20260915-1815";
        script.async = false;
        script.dataset.poigameCompactV2 = "1";
        document.head.appendChild(script);
      }
    }

    const indexThumbnailFor = (gameName, imageValue) => {
      const raw = String(imageValue || "").trim();
      if (!raw.startsWith("assets/game-art/")) return raw;

      const filename = raw.split("?", 1)[0].split("/").pop() || "";
      if (!/(?:\.(?:png|jpe?g))+$/i.test(filename)) return raw;

      let stem = filename;
      while (/\.(?:png|jpe?g)$/i.test(stem)) {
        stem = stem.replace(/\.(?:png|jpe?g)$/i, "");
      }
      return `assets/game-thumbs/${stem.toLowerCase()}.jpg`;
    };

    Object.defineProperty(window, "POIGAME_DATA", {
      configurable: true,
      get() {
        return poigameDataValue;
      },
      set(value) {
        if (value && typeof value.loadOffersWithFallback === "function" && typeof value.fetchCsv === "function") {
          if (isIndexPage && value.__poigameIndexThumbsPatched !== true) {
            const originalFetchCsv = value.fetchCsv.bind(value);
            value.fetchCsv = async function fetchCsvWithIndexThumbnails(path, ...args) {
              const rows = await originalFetchCsv(path, ...args);
              if (!Array.isArray(rows) || String(path || "").split("?", 1)[0] !== "games.csv") {
                return rows;
              }
              return rows.map((row) => ({
                ...row,
                image: indexThumbnailFor(row.name, row.image)
              }));
            };
            Object.defineProperty(value, "__poigameIndexThumbsPatched", {
              value: true,
              configurable: false,
              enumerable: false,
              writable: false
            });
          }

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
