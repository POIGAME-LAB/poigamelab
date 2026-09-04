(() => {
  "use strict";

  const root = document.querySelector("[data-poigame-header]") || (() => {
    const node = document.createElement("div");
    node.setAttribute("data-poigame-header", "");
    document.body.prepend(node);
    return node;
  })();

  document.querySelectorAll(".topbar").forEach((node) => node.remove());

  if (!document.getElementById("poigame-header-style")) {
    const style = document.createElement("style");
    style.id = "poigame-header-style";
    style.textContent = `
      :root {
        --poigame-purple: #7047ff;
        --poigame-deep: #241052;
        --poigame-ink: #2d1768;
        --poigame-line: #ece6fb;
        --poigame-yellow: #ffd93d;
      }

      .poigame-site-header {
        position: sticky;
        top: 0;
        z-index: 2147483002;
        width: 100%;
        border-bottom: 1px solid rgba(112,71,255,.12);
        background: rgba(255,255,255,.96);
        box-shadow: 0 8px 28px rgba(55,27,120,.07);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
      }

      .poigame-site-header__inner {
        width: min(1180px, calc(100% - 36px));
        min-height: 76px;
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 28px;
      }

      .poigame-site-header__logo {
        display: inline-flex;
        align-items: center;
        flex: 0 1 auto;
        text-decoration: none;
      }

      .poigame-site-header__logo img {
        display: block;
        width: 238px;
        max-width: 42vw;
        height: auto;
      }

      .poigame-site-header__nav {
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .poigame-site-header__nav a {
        display: inline-flex;
        align-items: center;
        min-height: 42px;
        padding: 0 13px;
        border-radius: 12px;
        color: #4b3a66;
        font-size: 13px;
        font-weight: 850;
        text-decoration: none;
        transition: background .18s ease, color .18s ease, transform .18s ease;
      }

      .poigame-site-header__nav a:hover,
      .poigame-site-header__nav a[aria-current="page"] {
        background: #f2eeff;
        color: var(--poigame-purple);
      }

      .poigame-site-header__nav a:hover { transform: translateY(-1px); }

      .poigame-site-header__nav a.poigame-site-header__contact {
        margin-left: 4px;
        border: 1px solid #ddd3ff;
        background: linear-gradient(135deg,#fff,#f7f4ff);
      }

      .poigame-site-header__menu {
        display: none;
        width: 44px;
        height: 44px;
        padding: 0;
        border: 0;
        border-radius: 13px;
        background: linear-gradient(145deg,#35127a,#7047ff);
        color: #fff;
        box-shadow: 0 8px 20px rgba(74,39,165,.24);
        cursor: pointer;
      }

      .poigame-site-header__menu span,
      .poigame-site-header__menu::before,
      .poigame-site-header__menu::after {
        content: "";
        display: block;
        width: 21px;
        height: 2px;
        margin: 4px auto;
        border-radius: 99px;
        background: currentColor;
        transition: transform .18s ease, opacity .18s ease;
      }

      .poigame-site-header__menu[aria-expanded="true"] span { opacity: 0; }
      .poigame-site-header__menu[aria-expanded="true"]::before { transform: translateY(6px) rotate(45deg); }
      .poigame-site-header__menu[aria-expanded="true"]::after { transform: translateY(-6px) rotate(-45deg); }

      .poigame-mobile-nav {
        display: none;
      }

      .poigame-context-bar {
        border-bottom: 1px solid var(--poigame-line);
        background: linear-gradient(90deg,#fbf9ff,#fffdf2);
      }

      .poigame-context-bar__inner {
        width: min(1180px, calc(100% - 36px));
        min-height: 42px;
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        color: #746887;
        font-size: 12px;
      }

      .poigame-context-bar a {
        color: var(--poigame-purple);
        font-weight: 900;
        text-decoration: none;
      }

      @media (max-width: 820px) {
        .poigame-site-header__inner {
          width: calc(100% - 28px);
          min-height: 66px;
          gap: 14px;
        }

        .poigame-site-header__logo img {
          width: 190px;
          max-width: 68vw;
        }

        .poigame-site-header__nav { display: none; }

        .poigame-site-header__menu {
          display: inline-block;
          flex: 0 0 auto;
        }

        .poigame-mobile-nav {
          position: fixed;
          inset: 66px 0 0 0;
          z-index: 2147483001;
          display: block;
          visibility: hidden;
          opacity: 0;
          pointer-events: none;
          transition: opacity .18s ease, visibility .18s ease;
        }

        .poigame-mobile-nav.is-open {
          visibility: visible;
          opacity: 1;
          pointer-events: auto;
        }

        .poigame-mobile-nav__scrim {
          position: absolute;
          inset: 0;
          background: rgba(25,12,58,.45);
          backdrop-filter: blur(4px);
          -webkit-backdrop-filter: blur(4px);
        }

        .poigame-mobile-nav__panel {
          position: absolute;
          top: 12px;
          right: 14px;
          width: min(calc(100vw - 28px), 360px);
          max-height: calc(100dvh - 92px);
          overflow-y: auto;
          padding: 10px;
          border: 1px solid rgba(255,255,255,.16);
          border-radius: 20px;
          background: linear-gradient(145deg,#28105f,#5c2fd7 64%,#7047ff);
          box-shadow: 0 22px 70px rgba(35,15,86,.42);
          -webkit-overflow-scrolling: touch;
        }

        .poigame-mobile-nav__panel a {
          display: flex;
          align-items: center;
          justify-content: space-between;
          min-height: 52px;
          padding: 0 14px;
          border-radius: 13px;
          color: #fff;
          font-size: 14px;
          font-weight: 900;
          text-decoration: none;
        }

        .poigame-mobile-nav__panel a + a {
          border-top: 1px solid rgba(255,255,255,.12);
        }

        .poigame-mobile-nav__panel a::after {
          content: "›";
          color: #ffe25a;
          font-size: 22px;
          line-height: 1;
        }

        .poigame-context-bar__inner {
          width: calc(100% - 28px);
          min-height: 40px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  const current = new URL(window.location.href);
  const filename = current.pathname.split("/").pop() || "index.html";

  const navItems = [
    ["ゲームを探す", "index.html#game-list"],
    ["案件一覧", "offers.html"],
    ["攻略一覧", "guides.html"],
    ["POIGAME LABとは", "about.html"],
    ["お問い合わせ", "contact.html"]
  ];

  const activeFor = (href) => {
    if (href === "index.html#game-list" && filename === "index.html") return true;
    if (href === "offers.html" && (filename === "offers.html" || filename === "game.html")) return true;
    if (href === "guides.html" && (filename === "guides.html" || filename.includes("guide") || filename.startsWith("township-lv"))) return true;
    return filename === href;
  };

  root.innerHTML = `
    <div class="poigame-site-header">
      <div class="poigame-site-header__inner">
        <a class="poigame-site-header__logo" href="index.html" aria-label="POIGAME LAB トップへ">
          <img src="poigamelab_logo_horizontal.png" alt="POIGAME LAB">
        </a>
        <nav class="poigame-site-header__nav" aria-label="メインメニュー">
          ${navItems.map(([label, href]) => `
            <a href="${href}" ${activeFor(href) ? 'aria-current="page"' : ""} class="${href === "contact.html" ? "poigame-site-header__contact" : ""}">${label}</a>
          `).join("")}
        </nav>
        <button class="poigame-site-header__menu" type="button" aria-label="メニューを開く" aria-expanded="false" aria-controls="poigame-mobile-nav"><span></span></button>
      </div>
    </div>
  `;

  document.getElementById("poigame-mobile-nav")?.remove();
  const mobileNav = document.createElement("div");
  mobileNav.id = "poigame-mobile-nav";
  mobileNav.className = "poigame-mobile-nav";
  mobileNav.setAttribute("aria-hidden", "true");
  mobileNav.innerHTML = `
    <div class="poigame-mobile-nav__scrim" data-menu-close></div>
    <nav class="poigame-mobile-nav__panel" aria-label="スマートフォンメニュー">
      ${navItems.map(([label, href]) => `<a href="${href}">${label}</a>`).join("")}
    </nav>
  `;
  document.body.appendChild(mobileNav);

  const button = root.querySelector(".poigame-site-header__menu");
  const scrim = mobileNav.querySelector("[data-menu-close]");

  const setOpen = (open) => {
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "メニューを閉じる" : "メニューを開く");
    mobileNav.classList.toggle("is-open", open);
    mobileNav.setAttribute("aria-hidden", String(!open));
    document.documentElement.style.overflow = open ? "hidden" : "";
    document.body.style.overflow = open ? "hidden" : "";
  };

  button.addEventListener("click", () => {
    setOpen(button.getAttribute("aria-expanded") !== "true");
  });

  scrim.addEventListener("click", () => setOpen(false));
  mobileNav.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setOpen(false)));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 820) setOpen(false);
  });
})();
