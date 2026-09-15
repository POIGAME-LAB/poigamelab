(() => {
  "use strict";

  window.POIGAME_IMAGE_RIGHTS = Object.freeze({
    "ワーキングヒーロー": Object.freeze({
      credit: "画像出典：ワーキングヒーローズ公式サイト"
    })
  });

  const pathname = String(window.location.pathname || "");
  const isCompactIndex = pathname === "/" || /\/index\.html$/.test(pathname);

  const quarantinedImages = new Set([
    "assets/game-art/mementomori.webp"
  ]);

  const cacheBustImages = new Map([
    ["assets/game-art/township-original.jpeg", "20260908-0120"],
    ["assets/game-art/kinoko-original.png", "20260908-0120"],
    ["assets/game-art/whiteout-survival.svg", "20260906-2355"],
    ["assets/game-art/tokyo-debunker.jpeg", "20260907-1208"]
  ]);

  const applyCacheBust = (img) => {
    if (!(img instanceof HTMLImageElement)) return;
    const rawSrc = String(img.getAttribute("src") || "").trim();
    const version = cacheBustImages.get(rawSrc);
    if (!version || rawSrc.includes("?v=")) return;
    img.setAttribute("src", `${rawSrc}?v=${version}`);
  };

  const gameNameFromAlt = (img) =>
    String(img.getAttribute("alt") || "ゲームイメージ").replace(/\s*イメージ\s*$/, "") || "ゲームイメージ";

  const makeCardFallback = (gameName) => {
    const box = document.createElement("div");
    box.className = "image-placeholder";
    const small = document.createElement("small");
    small.textContent = "POIGAME LAB";
    const strong = document.createElement("strong");
    strong.textContent = gameName;
    box.append(small, strong);
    return box;
  };

  const makeDetailFallback = (gameName) => {
    const box = document.createElement("div");
    box.className = "game-artwork-fallback";
    const small = document.createElement("small");
    small.textContent = "POIGAME LAB";
    const strong = document.createElement("strong");
    strong.textContent = gameName;
    box.append(small, strong);
    return box;
  };

  const replaceBrokenArtwork = (img) => {
    if (!(img instanceof HTMLImageElement) || img.dataset.poigameFallbackApplied === "1") return;

    const rawSrc = String(img.getAttribute("src") || "").split("?", 1)[0].trim();
    const shouldQuarantine = quarantinedImages.has(rawSrc);
    const isGameArtwork = img.classList.contains("game-thumbnail") || Boolean(img.closest(".game-artwork"));
    if (!shouldQuarantine && !isGameArtwork) return;

    img.dataset.poigameFallbackApplied = "1";
    const gameName = gameNameFromAlt(img);

    if (img.classList.contains("game-thumbnail")) {
      img.replaceWith(makeCardFallback(gameName));
      return;
    }

    if (img.closest(".game-artwork")) {
      img.replaceWith(makeDetailFallback(gameName));
    }
  };

  const inspectNode = (node) => {
    if (!(node instanceof Element)) return;

    if (node.matches("img")) {
      applyCacheBust(node);
      const src = String(node.getAttribute("src") || "").split("?", 1)[0].trim();
      if (quarantinedImages.has(src)) replaceBrokenArtwork(node);
    }

    node.querySelectorAll?.("img").forEach((img) => {
      applyCacheBust(img);
      const src = String(img.getAttribute("src") || "").split("?", 1)[0].trim();
      if (quarantinedImages.has(src)) replaceBrokenArtwork(img);
    });
  };

  document.addEventListener("error", (event) => {
    if (event.target instanceof HTMLImageElement) replaceBrokenArtwork(event.target);
  }, true);

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach(inspectNode);
    }
  });

  const startObserver = () => {
    document.querySelectorAll("img").forEach((img) => {
      applyCacheBust(img);
      const src = String(img.getAttribute("src") || "").split("?", 1)[0].trim();
      if (quarantinedImages.has(src)) replaceBrokenArtwork(img);
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver, { once: true });
  } else {
    startObserver();
  }

  const style = document.createElement("style");
  style.textContent = `
    .game-thumbnail[src*="w-heroes.com/img/sp/key_visual.png"],
    .game-artwork img[src*="w-heroes.com/img/sp/key_visual.png"] {
      object-fit: contain !important;
      background: #ffffff;
    }
  `;
  document.head.appendChild(style);

  if (!isCompactIndex) return;

  document.documentElement.classList.add("poigame-index-compact");

  const compactStyle = document.createElement("style");
  compactStyle.id = "poigame-index-compact-style";
  compactStyle.textContent = `
    .poigame-index-compact body {
      background: #fbfaff;
    }

    .poigame-index-compact .hero {
      background: linear-gradient(180deg,#ffffff 0%,#f8f5ff 100%);
    }

    .poigame-index-compact .hero-visual {
      display: none !important;
    }

    .poigame-index-compact .search-area {
      padding: 24px 16px;
      background: #ffffff;
    }

    .poigame-index-compact .search-frame {
      max-width: 780px;
      border-radius: 19px;
      box-shadow: 0 10px 28px rgba(76,40,160,.12);
    }

    .poigame-index-compact .search-box {
      padding: 6px;
      border-radius: 15px;
    }

    .poigame-index-compact .search-box input,
    .poigame-index-compact .search-box button {
      height: 48px;
    }

    .poigame-index-compact .lab-dashboard {
      max-width: 980px;
      margin: 0 auto;
      padding: 0 16px 20px;
    }

    .poigame-index-compact .lab-dashboard-inner {
      gap: 10px;
      padding: 15px;
      border-radius: 21px;
      box-shadow: 0 14px 34px rgba(58,25,130,.19);
    }

    .poigame-index-compact .dashboard-lead {
      padding: 7px 9px;
    }

    .poigame-index-compact .dashboard-stat {
      min-height: 78px;
      padding: 11px;
      border-radius: 14px;
    }

    .poigame-index-compact .featured-games {
      max-width: 1040px;
      padding: 28px 16px 60px;
    }

    .poigame-index-compact .section-heading {
      margin-bottom: 15px;
    }

    .poigame-index-compact .section-heading h2 {
      font-size: 24px;
    }

    .poigame-index-compact .sort-buttons {
      gap: 8px;
      margin-bottom: 16px;
    }

    .poigame-index-compact .sort-buttons button {
      min-height: 42px;
      padding: 8px 14px;
      font-size: 12px;
    }

    .poigame-index-compact .game-grid {
      grid-template-columns: repeat(3,minmax(0,1fr));
      gap: 14px;
    }

    .poigame-index-compact .game-card {
      display: grid;
      grid-template-columns: 76px minmax(0,1fr);
      column-gap: 12px;
      padding: 14px;
      overflow: hidden;
      border-radius: 18px;
      box-shadow: 0 7px 22px rgba(73,40,145,.08);
    }

    .poigame-index-compact .game-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 10px 26px rgba(73,40,145,.12);
    }

    .poigame-index-compact .game-image {
      display: block !important;
      grid-column: 1;
      grid-row: 1 / span 3;
      align-self: start;
      width: 76px;
      padding: 0 !important;
    }

    .poigame-index-compact .game-image .game-thumbnail,
    .poigame-index-compact .game-image .image-placeholder {
      display: flex;
      width: 76px;
      height: 76px;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      border-radius: 14px;
      box-shadow: 0 5px 14px rgba(48,22,108,.12);
    }

    .poigame-index-compact .game-image .image-placeholder {
      padding: 7px;
      justify-content: flex-end;
    }

    .poigame-index-compact .game-image .image-placeholder small {
      margin-bottom: 3px;
      font-size: 6px;
      letter-spacing: .6px;
    }

    .poigame-index-compact .game-image .image-placeholder strong {
      max-width: 100%;
      font-size: 10px;
      line-height: 1.15;
    }

    .poigame-index-compact .game-image .image-rights-note {
      display: none;
    }

    .poigame-index-compact .game-info {
      display: contents;
    }

    .poigame-index-compact .card-rank-row,
    .poigame-index-compact .game-info h3,
    .poigame-index-compact .game-condition {
      grid-column: 2;
      min-width: 0;
    }

    .poigame-index-compact .card-rank-row {
      min-height: 0;
      margin-bottom: 5px;
    }

    .poigame-index-compact .rank-badge {
      padding: 5px 10px;
      font-size: 10px;
    }

    .poigame-index-compact .game-info h3 {
      margin: 0 0 3px;
      font-size: 18px;
      line-height: 1.3;
    }

    .poigame-index-compact .game-condition {
      margin: 0;
      color: #8b839d;
      font-size: 11px;
      line-height: 1.45;
    }

    .poigame-index-compact .reward-box,
    .poigame-index-compact .point-site,
    .poigame-index-compact .verification-line,
    .poigame-index-compact .game-meta,
    .poigame-index-compact .card-actions,
    .poigame-index-compact .offer-button,
    .poigame-index-compact .referral-button,
    .poigame-index-compact .referral-code {
      grid-column: 1 / -1;
    }

    .poigame-index-compact .reward-box {
      align-items: center;
      margin: 12px 0 9px;
      padding: 10px 12px;
      border-radius: 12px;
    }

    .poigame-index-compact .reward-box strong {
      font-size: 20px;
    }

    .poigame-index-compact .point-site {
      min-height: 0;
      margin: 0 0 9px;
      font-size: 11px;
    }

    .poigame-index-compact .verification-line {
      margin: 5px 0 8px;
      font-size: 10px;
    }

    .poigame-index-compact .game-meta {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-bottom: 0;
    }

    .poigame-index-compact .game-meta span {
      min-width: 0;
      padding: 8px 7px;
      border-radius: 9px;
      font-size: 10px;
      line-height: 1.45;
    }

    .poigame-index-compact .card-actions {
      gap: 7px;
      margin-top: 10px;
    }

    .poigame-index-compact .card-action {
      min-height: 41px;
      padding: 8px 9px;
      border-radius: 10px;
      font-size: 12px;
    }

    .poigame-index-compact .offer-button {
      margin-top: 8px;
      padding: 9px 11px;
      border-radius: 10px;
      font-size: 12px;
    }

    .poigame-index-compact .referral-button {
      margin-top: 6px;
      padding: 7px 10px;
      border-radius: 9px;
      font-size: 10px;
    }

    .poigame-index-compact .referral-code {
      margin-top: 3px;
      font-size: 9px;
    }

    @media (max-width: 800px) {
      .poigame-index-compact .search-area {
        padding: 16px 12px;
      }

      .poigame-index-compact .search-frame {
        padding: 3px;
        border-radius: 17px;
      }

      .poigame-index-compact .search-box {
        gap: 5px;
        padding: 5px;
        border-radius: 14px;
      }

      .poigame-index-compact .search-icon {
        padding-left: 9px;
        font-size: 18px;
      }

      .poigame-index-compact .search-box input {
        padding: 0 7px;
      }

      .poigame-index-compact .search-box button {
        min-width: 80px;
      }

      .poigame-index-compact .lab-dashboard {
        padding: 0 12px 16px;
        margin-top: 0;
      }

      .poigame-index-compact .lab-dashboard-inner {
        grid-template-columns: repeat(3,minmax(0,1fr));
        gap: 7px;
        padding: 11px;
        border-radius: 18px;
      }

      .poigame-index-compact .dashboard-lead {
        grid-column: 1 / -1;
        padding: 4px 3px 7px;
      }

      .poigame-index-compact .dashboard-lead small {
        font-size: 9px;
      }

      .poigame-index-compact .dashboard-lead h2 {
        margin-top: 3px;
        font-size: 18px;
      }

      .poigame-index-compact .dashboard-lead p {
        font-size: 10px;
      }

      .poigame-index-compact .dashboard-stat,
      .poigame-index-compact .dashboard-stat:last-child {
        grid-column: auto;
        min-height: 67px;
        padding: 8px;
        border-radius: 12px;
      }

      .poigame-index-compact .dashboard-stat span {
        font-size: 9px;
        line-height: 1.3;
      }

      .poigame-index-compact .dashboard-stat strong {
        margin-top: 3px;
        font-size: 14px;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }

      .poigame-index-compact .featured-games {
        padding: 22px 12px 50px;
      }

      .poigame-index-compact .section-heading {
        align-items: flex-end;
        gap: 8px;
        margin-bottom: 12px;
      }

      .poigame-index-compact .section-label {
        margin-bottom: 3px;
        font-size: 10px;
      }

      .poigame-index-compact .section-heading h2 {
        font-size: 20px;
        line-height: 1.35;
      }

      .poigame-index-compact .view-all {
        flex: 0 0 auto;
        font-size: 11px;
      }

      .poigame-index-compact .sort-buttons {
        flex-wrap: nowrap;
        overflow-x: auto;
        gap: 7px;
        margin: 0 -2px 13px;
        padding: 0 2px 3px;
        scrollbar-width: none;
        -webkit-overflow-scrolling: touch;
      }

      .poigame-index-compact .sort-buttons::-webkit-scrollbar {
        display: none;
      }

      .poigame-index-compact .sort-buttons button {
        flex: 0 0 auto;
        min-height: 40px;
        padding: 8px 13px;
        font-size: 11px;
      }

      .poigame-index-compact .game-grid {
        grid-template-columns: 1fr;
        gap: 12px;
      }

      .poigame-index-compact .game-card {
        grid-template-columns: 82px minmax(0,1fr);
        column-gap: 12px;
        padding: 13px;
      }

      .poigame-index-compact .game-image,
      .poigame-index-compact .game-image .game-thumbnail,
      .poigame-index-compact .game-image .image-placeholder {
        width: 82px;
        height: 82px;
      }

      .poigame-index-compact .game-info h3 {
        font-size: 19px;
      }

      .poigame-index-compact .reward-box strong {
        font-size: 22px;
      }

      .poigame-index-compact .game-meta span {
        font-size: 10px;
      }
    }
  `;
  document.head.appendChild(compactStyle);
})();
