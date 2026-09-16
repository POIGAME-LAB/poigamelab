(() => {
  "use strict";

  if (document.querySelector("[data-poigame-footer]")) return;

  if (!document.querySelector('link[rel="icon"]')) {
    const icon = document.createElement("link");
    icon.rel = "icon";
    icon.href = "poigamelab_icon.png";
    document.head.appendChild(icon);
  }

  if (!document.getElementById("poigame-footer-style")) {
    const style = document.createElement("style");
    style.id = "poigame-footer-style";
    style.textContent = `
      .poigame-footer {
        margin-top: 48px;
        padding: 28px 18px 34px;
        border-top: 1px solid #e9e3f7;
        background: #faf8ff;
        color: #706780;
        font-size: 12px;
        line-height: 1.7;
        text-align: center;
      }
      .poigame-footer__links {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 10px 18px;
        margin-bottom: 12px;
      }
      .poigame-footer a {
        color: #5b35b5;
        font-weight: 700;
        text-decoration: none;
      }
      .poigame-footer a:hover { text-decoration: underline; }
      .poigame-footer__note {
        max-width: 760px;
        margin: 0 auto 10px;
      }
      .poigame-footer__copy { margin: 0; }
    `;
    document.head.appendChild(style);
  }

  const footer = document.createElement("footer");
  footer.className = "poigame-footer";
  footer.setAttribute("data-poigame-footer", "");
  footer.innerHTML = `
    <nav class="poigame-footer__links" aria-label="サイト情報">
      <a href="offers.html">案件一覧</a>
      <a href="guides.html">攻略一覧</a>
      <a href="about.html">運営情報・免責事項</a>
      <a href="privacy.html">プライバシーポリシー</a>
      <a href="contact.html">お問い合わせ</a>
    </nav>
    <p class="poigame-footer__note">
      案件の報酬・条件・掲載状況は変動します。申込み前に必ずリンク先のポイントサイトで最新条件をご確認ください。
    </p>
    <p class="poigame-footer__copy">© 2026 POIGAME LAB</p>
  `;
  document.body.appendChild(footer);
})();

(() => {
  "use strict";
  if (document.documentElement.hasAttribute("data-poigame-analytics-installed")) return;
  document.documentElement.setAttribute("data-poigame-analytics-installed", "");

  const send = (name, params = {}) => {
    if (typeof window.gtag !== "function") return;
    window.gtag("event", name, {
      page_path: location.pathname + location.search,
      ...params
    });
  };

  const textOf = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120);
  const gameFromPage = () => new URLSearchParams(location.search).get("game") || "";

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const a = target.closest("a[href]");
    if (a) {
      const href = a.getAttribute("href") || "";
      let url;
      try { url = new URL(a.href, location.href); } catch { url = null; }
      const params = {
        link_text: textOf(a),
        link_url: url?.href || href,
        game_name: gameFromPage()
      };

      if (a.matches(".offer-button,.offer-link,.referral-button,.referral-link")) {
        send("affiliate_click", params);
      } else if (a.matches(".card-action") || /#comparison(?:$|\?)/.test(href) || /game\.html\?game=/.test(href)) {
        if (/comparison/.test(href) || textOf(a).includes("比較")) send("comparison_click", params);
        else send("game_detail_click", params);
      } else if (a.matches(".card-action--guide,.guide,.compare") || /-guide\.html/.test(href) || textOf(a).includes("攻略")) {
        send("guide_click", params);
      } else if (url && url.origin !== location.origin) {
        send("outbound_click", {
          ...params,
          destination_host: url.hostname
        });
      } else {
        send("internal_link_click", params);
      }
    }

    const sort = target.closest(".sort-buttons button");
    if (sort) send("sort_click", { sort_label: textOf(sort) });

    const os = target.closest(".os-filter button");
    if (os) send("os_filter_click", {
      platform: os.getAttribute("data-platform") || textOf(os),
      game_name: gameFromPage()
    });

    if (target.closest(".search-box button,#offerSearchButton")) {
      const input = document.querySelector(".search-box input,#offerSearch");
      send("site_search", { search_term: String(input?.value || "").trim().slice(0, 100) });
    }
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const el = event.target;
    if (!(el instanceof HTMLInputElement)) return;
    if (!el.matches(".search-box input,#offerSearch")) return;
    send("site_search", { search_term: el.value.trim().slice(0, 100) });
  }, true);
})();

(() => {
  "use strict";
  if (!/\/township-lv70\.html$/.test(location.pathname)) return;
  if (document.documentElement.hasAttribute("data-township-hq-images")) return;
  document.documentElement.setAttribute("data-township-hq-images", "");

  const v = "20260914-0053";
  const base = "assets/township-experience/";

  const makeFigure = (src, alt, caption, extraClass = "") => {
    const figure = document.createElement("figure");
    figure.className = `figure ${extraClass}`.trim();
    figure.setAttribute("data-township-hq", "");
    const img = document.createElement("img");
    img.src = src;
    img.alt = alt;
    img.loading = "lazy";
    const cap = document.createElement("figcaption");
    cap.textContent = caption;
    figure.append(img, cap);
    return figure;
  };

  const replaceSrc = (match, src) => {
    const img = [...document.images].find((el) => (el.getAttribute("src") || "").includes(match));
    if (img) img.src = src;
  };

  replaceSrc("lv70-achieved.jpg", `${base}lv70-achieved.png?v=${v}`);
  replaceSrc("card-exchange-redacted.jpg", `${base}card-exchange-redacted.png?v=${v}`);

  const result = document.querySelector("#result");
  if (result && !result.querySelector('[data-township-hq="result-town"]')) {
    const fig = makeFigure(`${base}lv70-town.png?v=${v}`, "TownshipでLv70到達後の街の実プレイ画面", "Lv70到達後の街。後半はヘリコプター注文と桜の木を中心に経験値を伸ばしました。");
    fig.setAttribute("data-township-hq", "result-town");
    result.appendChild(fig);
  }

  const heli = document.querySelector("#heli");
  if (heli && !heli.querySelector('[data-township-hq="heli"]')) {
    const fig = makeFigure(`${base}helicopter-order.jpg?v=${v}`, "Townshipのヘリコプター注文の実プレイ画面", "後半のレベル上げで中心に回したヘリコプター注文。");
    fig.setAttribute("data-township-hq", "heli");
    heli.appendChild(fig);
  }

  const boost = document.querySelector("#boost");
  if (boost && !boost.querySelector('[data-township-hq="boost"]')) {
    const fig = makeFigure(`${base}research-boosts.jpg?v=${v}`, "Township研究所の活気ある市場と気前のいい顧客", "研究所では「活気ある市場」と「気前のいい顧客」を使ってヘリ周回を加速しました。");
    fig.setAttribute("data-township-hq", "boost");
    boost.appendChild(fig);
  }

  const cherry = document.querySelector("#cherry");
  if (cherry && !cherry.querySelector('[data-township-hq="cherry"]')) {
    const wrap = document.createElement("div");
    wrap.className = "grid2";
    wrap.setAttribute("data-township-hq", "cherry");
    wrap.append(
      makeFigure(`${base}sakura-price.png?v=${v}`, "Townshipの桜の木が9000コインで購入できる画面", "桜の木はプレイ時点で1本9,000コインでした。"),
      makeFigure(`${base}sakura-exp.png?v=${v}`, "Townshipで桜の木購入時に990EXPを獲得した画面", "桜の木の購入時に990EXPを獲得できました。")
    );
    const note = cherry.querySelector(".mini-note");
    if (note) cherry.insertBefore(wrap, note); else cherry.appendChild(wrap);
  }

  const pass = document.querySelector("#pass");
  if (pass && !pass.querySelector('[data-township-hq="pass"]')) {
    const src = `${base}harvest-pass.heic?v=${v}`;
    const probe = new Image();
    probe.onload = () => {
      if (pass.querySelector('[data-township-hq="pass"]')) return;
      const fig = makeFigure(src, "Townshipハーベストパスの実プレイ画面", "実際に購入したハーベストパス。市場の商品×2や納屋の広さ+30%が後半のまとめプレイで役立ちました。");
      fig.setAttribute("data-township-hq", "pass");
      const warning = pass.querySelector(".warning");
      if (warning) pass.insertBefore(fig, warning); else pass.appendChild(fig);
    };
    probe.src = src;
  }

  const puzzle = document.querySelector("#puzzle");
  if (puzzle && !puzzle.querySelector('[data-township-hq="puzzle"]')) {
    const fig = makeFigure(`${base}puzzle-2000-reward.jpg?v=${v}`, "Townshipパズル2000到達時の実プレイ報酬画面", "パズル2000到達時の報酬画面。Lv70目的ならここまで進める必要はありませんでした。");
    fig.setAttribute("data-township-hq", "puzzle");
    puzzle.appendChild(fig);
  }
})();

(() => {
  const script = document.createElement('script');
  script.src = 'assets/current-offers.js';
  document.body.appendChild(script);
})();
