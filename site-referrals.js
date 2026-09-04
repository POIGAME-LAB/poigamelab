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
    })
  });

  function get(siteId) {
    const key = String(siteId || "").trim().toLowerCase();
    return referrals[key] || null;
  }

  window.POIGAME_REFERRALS = Object.freeze({
    get,
    referrals
  });
})();
