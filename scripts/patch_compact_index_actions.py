#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGET = Path("_site/index.html")
MARKER = "POIGAME_COMPACT_ACTIONS_V6"

PATCH = r'''
<!-- POIGAME_COMPACT_ACTIONS_V6 -->
<style id="poigame-compact-actions-v6">
@media (max-width: 800px) {
  body .game-card .card-actions {
    display: grid !important;
    grid-template-columns: minmax(0,.9fr) minmax(0,.9fr) minmax(0,1.35fr) !important;
    gap: 5px !important;
    width: 100% !important;
    margin: 5px 0 0 !important;
  }

  body .game-card .card-actions > .card-action,
  body .game-card .card-actions > .offer-button {
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

  body .game-card .card-actions > :first-child {
    grid-column: 1 !important;
    order: 1 !important;
  }

  body .game-card .card-actions > :nth-child(2) {
    grid-column: 2 !important;
    order: 2 !important;
  }

  body .game-card .card-actions > .offer-button {
    grid-column: 3 !important;
    order: 3 !important;
    background: linear-gradient(145deg,#ffe56a,#ffd23f) !important;
    color: #33165e !important;
  }

  body .game-card .referral-strip {
    grid-column: 1 / -1 !important;
    grid-row: 7 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    width: 100% !important;
    min-height: 20px !important;
    height: 20px !important;
    margin: 4px 0 0 !important;
    padding: 2px 8px !important;
    border: 1px solid #e3dcfb !important;
    border-radius: 7px !important;
    background: #fbfaff !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
  }

  body .game-card .referral-strip .referral-button,
  body .game-card .referral-strip .referral-code {
    display: inline !important;
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
  }

  body .game-card .referral-strip .referral-button {
    color: #5d34da !important;
    font-size: 8.2px !important;
    font-weight: 900 !important;
    text-decoration: none !important;
  }

  body .game-card .referral-strip .referral-code {
    color: #81788e !important;
    font-size: 7.8px !important;
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
        print("compact action V6 patch already present")
        return 0
    if "</body>" not in html:
        raise SystemExit("index.html missing </body>")

    TARGET.write_text(html.replace("</body>", f"{PATCH}\n</body>", 1), encoding="utf-8")
    print("patched explicit action order and compact referral bar into _site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
