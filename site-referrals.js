(() => {
  "use strict";

  const referrals = Object.freeze({
    moppy: Object.freeze({
      site: "moppy",
      name: "モッピー",
      url: "https://pc.moppy.jp/entry/invite.php?invite=Jh7He170",
      code: "Jh7He170",
      disclosure: "PR"
    }),
    warau: Object.freeze({
      site: "warau",
      name: "ワラウ",
      url: "https://www.warau.jp/friend/reg/d5em",
      code: "d5eo",
      disclosure: "PR"
    }),
    hapitas: Object.freeze({
      site: "hapitas",
      name: "ハピタス",
      url: "https://hapitas.jp/appinvite?i=23001138&route=text",
      code: "WSOVBE",
      disclosure: "PR"
    }),
    chobirich: Object.freeze({
      site: "chobirich",
      name: "ちょびリッチ",
      url: "https://www.chobirich.com/cm/ad/?p=8225208671&i=4089943",
      code: "rhbzgK",
      disclosure: "PR"
    }),
    coincome: Object.freeze({
      site: "coincome",
      name: "COINCOME",
      url: "https://cimcome.jp/join?code=6e64a861b226ce831774df6133745ca48a54fa4b9dcaf92ec615dd0a339cee4b",
      code: "lCpwnBGu",
      disclosure: "PR"
    }),
    mikoshi: Object.freeze({
      site: "mikoshi",
      name: "MIKOSHI",
      url: "",
      code: "RKG8XRE7V4Y3EQV6",
      disclosure: "PR"
    }),
    gendama: Object.freeze({
      site: "gendama",
      name: "げん玉",
      url: "https://www.gendama.jp/invite/?frid=7536053&ref=90000-url",
      code: "it4dS1cG",
      disclosure: "PR"
    }),
    kurashiru_reward: Object.freeze({
      site: "kurashiru_reward",
      name: "クラシルリワード（レシチャレ）",
      url: "https://www.rewards.kurashiru.com/register?ref=7dca6645-3901-4dd1-847a-90b4bfa511c0",
      code: "LJZUC02M",
      disclosure: "PR"
    }),
    amefuri: Object.freeze({
      site: "amefuri",
      name: "アメフリ",
      url: "https://www.amefri.net/register?inv=f231110",
      code: "poigamelab0",
      disclosure: "PR"
    }),
    point_town: Object.freeze({
      site: "point_town",
      name: "ポイントタウン",
      url: "https://www.pointtown.com/registration?intrid=et9brwfjafEs3",
      code: "et9brwUQXJjiB",
      disclosure: "PR"
    }),
    ec_navi: Object.freeze({
      site: "ec_navi",
      name: "ECナビ",
      url: "https://ecnavi.jp/invite/?id=rtyeu",
      code: "rtyeu",
      disclosure: "PR"
    })
  });

  const referralAliases = Object.freeze({
    pointtown: "point_town",
    ecnavi: "ec_navi",
    ecnav: "ec_navi"
  });

  function get(siteId) {
    const key = String(siteId || "").trim().toLowerCase();
    const normalizedKey = referralAliases[key] || key;
    return referrals[normalizedKey] || null;
  }

  window.POIGAME_REFERRALS = Object.freeze({
    get,
    referrals
  });
})();
