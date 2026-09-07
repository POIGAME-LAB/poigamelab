(() => {
  "use strict";

  // Register only artwork that requires a visible rights notice.
  // User-approved or POIGAME LAB original artwork should not be added here.
  window.POIGAME_IMAGE_RIGHTS = Object.freeze({
    "ワーキングヒーロー": Object.freeze({
      credit: "画像出典：ワーキングヒーローズ公式サイト"
    })
  });

  // Keep only artwork whose source file is still known-bad in quarantine.
  // Township and Kinoko were re-imported from the user's intact uploads.
  const quarantinedImages = new Set([
    "assets/game-art/mementomori.webp"
  ]);

  // These paths were previously served with corrupted binaries. Add a version
  // only at render time so browsers are forced to fetch the newly verified files.
  const cacheBustImages = new Map([
    ["assets/game-art/township.webp", "20260906-2355"],
    ["assets/game-art/kinoko.webp", "20260906-2355"],
    ["assets/game-art/whiteout-survival.svg", "20260906-2355"],
    ["assets/game-art/tokyo-debunker.jpeg", "20260907-1208"]
  ]);

  const applyCacheBust = (img) => {
    if (!(img instanceof HTMLImageElement)) return;
    const rawSrc = String(img.getAttribute("src") || "").trim();
    const version = cacheBustImages.get(rawSrc);
    if (!version) return;
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

    const rawSrc = String(img.getAttribute("src") || "").trim();
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
      const src = String(node.getAttribute("src") || "").trim();
      if (quarantinedImages.has(src)) replaceBrokenArtwork(node);
    }
    node.querySelectorAll?.("img").forEach((img) => {
      applyCacheBust(img);
      const src = String(img.getAttribute("src") || "").trim();
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
      const src = String(img.getAttribute("src") || "").trim();
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
})();
