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
