(() => {
  "use strict";

  const pathname = String(window.location.pathname || "");
  const isIndexPage = pathname === "/" || /\/index\.html$/.test(pathname);
  if (!isIndexPage) return;

  const compactDays = (text) => {
    const raw = String(text || "").replace(/^⏱\s*達成目安[:：]\s*/, "").trim();
    const range = raw.match(/\d+\s*[〜～-]\s*\d+日/);
    if (range) return `⏱ 達成目安：${range[0].replace(/\s+/g, "")}`;
    const day = raw.match(/\d+日/);
    if (day) return `⏱ 達成目安：${day[0]}`;
    const short = raw.split(/[／/]/)[0].replace(/^Lv\d+[:：]?\s*/, "").trim();
    return `⏱ 達成目安：${short || "調査中"}`;
  };

  const compactDifficulty = (text) => {
    let raw = String(text || "").replace(/^🎮\s*難易度[:：]\s*/, "").trim();
    raw = raw.split(/[／/]/)[0].replace(/^Lv\d+[:：]?\s*/, "").trim();
    raw = raw.replace(/[（(].*?[）)]/g, "").trim();
    return `🎮 難易度：${raw || "調査中"}`;
  };

  const compactCard = (card) => {
    if (!(card instanceof HTMLElement) || !card.classList.contains("game-card")) return;

    const actions = card.querySelector(".card-actions");
    const offer = card.querySelector(":scope > .game-info > .offer-button, :scope > .offer-button");
    if (actions && offer && offer.parentElement !== actions) {
      actions.appendChild(offer);
    }

    const meta = card.querySelectorAll(".game-meta span");
    if (meta[0] && meta[0].dataset.compactV2 !== "1") {
      meta[0].textContent = compactDays(meta[0].textContent);
      meta[0].dataset.compactV2 = "1";
    }
    if (meta[1] && meta[1].dataset.compactV2 !== "1") {
      meta[1].textContent = compactDifficulty(meta[1].textContent);
      meta[1].dataset.compactV2 = "1";
    }

    card.classList.add("is-dense-v2");
  };

  const scan = (root = document) => {
    root.querySelectorAll?.(".game-card").forEach(compactCard);
  };

  const start = () => {
    scan();
    const target = document.querySelector(".game-grid") || document.body;
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          if (node.matches(".game-card")) compactCard(node);
          scan(node);
        });
      }
    });
    observer.observe(target, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
