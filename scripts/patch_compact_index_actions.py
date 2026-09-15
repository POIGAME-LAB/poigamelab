#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGET = Path("_site/index.html")
MARKER = "POIGAME_COMPACT_ACTIONS_V8"

PATCH = r'''
<!-- POIGAME_COMPACT_ACTIONS_V8 -->
<style id="poigame-compact-actions-v8">
@media (max-width: 800px) {
  html.poigame-index-compact body .game-card.is-dense-v2 {
    grid-template-rows: auto auto auto auto auto auto minmax(16px, auto) !important;
    padding-bottom: 9px !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .card-actions {
    display: grid !important;
    grid-template-columns: minmax(0,.9fr) minmax(0,.9fr) minmax(0,1.35fr) !important;
    gap: 5px !important;
    width: 100% !important;
    margin: 5px 0 0 !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .card-actions > .card-action,
  html.poigame-index-compact body .game-card.is-dense-v2 .card-actions > .offer-button {
    grid-row: 1 !important;
    min-width: 0 !important;
    width: 100% !important;
    min-height: 29px !important;
    height: 29px !important;
    margin: 0 !important;
    padding: 4px 3px !important;
    border-radius: 8px !important;
    font-size: 9px !important;
    line-height: 1.05 !important;
    white-space: nowrap !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .card-actions > :first-child {
    grid-column: 1 !important;
    order: 1 !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .card-actions > :nth-child(2) {
    grid-column: 2 !important;
    order: 2 !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .card-actions > .offer-button {
    grid-column: 3 !important;
    order: 3 !important;
    background: linear-gradient(145deg,#ffe56a,#ffd23f) !important;
    color: #33165e !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip {
    grid-column: 1 / -1 !important;
    grid-row: 7 !important;
    align-self: center !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 7px !important;
    width: 100% !important;
    min-height: 15px !important;
    height: 15px !important;
    margin: 3px 0 0 !important;
    padding: 0 7px !important;
    border: 1px solid #e5dffd !important;
    border-radius: 6px !important;
    background: #fbfaff !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-button,
  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-code {
    display: inline !important;
    flex: 0 1 auto !important;
    grid-column: auto !important;
    grid-row: auto !important;
    min-width: 0 !important;
    width: auto !important;
    min-height: 0 !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    line-height: 1 !important;
    white-space: nowrap !important;
    overflow: visible !important;
    text-overflow: clip !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-button {
    color: #5d34da !important;
    font-size: 7.5px !important;
    font-weight: 900 !important;
    text-decoration: none !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-code {
    color: #81788e !important;
    font-size: 7.2px !important;
    font-weight: 700 !important;
  }
}
</style>
<script>
(() => {
  "use strict";

  const fixCard = (card) => {
    if (!(card instanceof HTMLElement) || !card.classList.contains("game-card")) return;

    const actions = card.querySelector(".card-actions");
    const offer = card.querySelector(".offer-button");
    if (actions && offer && offer.parentElement !== actions) {
      actions.appendChild(offer);
    }

    const referralButton = card.querySelector(".referral-button");
    const referralCode = card.querySelector(".referral-code");
    if (!referralButton) return;

    let strip = card.querySelector(".referral-strip");
    if (!strip) {
      strip = document.createElement("div");
      strip.className = "referral-strip";
      if (actions) actions.insertAdjacentElement("afterend", strip);
      else card.appendChild(strip);
    }

    referralButton.textContent = "このサイトに登録［PR］";
    if (referralButton.parentElement !== strip) strip.appendChild(referralButton);
    if (referralCode && referralCode.parentElement !== strip) strip.appendChild(referralCode);
  };

  const scan = (root = document) => {
    root.querySelectorAll?.(".game-card").forEach(fixCard);
  };

  const start = () => {
    scan();
    const target = document.querySelector(".game-grid") || document.body;
    new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          if (node.matches(".game-card")) fixCard(node);
          scan(node);
        });
      }
    }).observe(target, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
</script>
'''.strip()


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"missing target: {TARGET}")

    html = TARGET.read_text(encoding="utf-8")
    if MARKER in html:
        print("compact action V8 patch already present")
        return 0
    if "</body>" not in html:
        raise SystemExit("index.html missing </body>")

    TARGET.write_text(html.replace("</body>", f"{PATCH}\n</body>", 1), encoding="utf-8")
    print("patched V8 action order and high-specificity referral bar into _site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
