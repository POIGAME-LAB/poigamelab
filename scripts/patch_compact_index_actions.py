#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGET = Path("_site/index.html")
MARKER = "POIGAME_COMPACT_ACTIONS_V3"

PATCH = r'''
<!-- POIGAME_COMPACT_ACTIONS_V3 -->
<style id="poigame-compact-actions-v3">
@media (max-width: 800px) {
  html.poigame-index-compact .game-card.is-dense-v2 .card-actions,
  .game-card.is-dense-v2 .card-actions {
    grid-template-columns: .9fr .9fr 1.35fr !important;
    gap: 5px !important;
    margin-top: 5px !important;
  }

  html.poigame-index-compact .game-card.is-dense-v2 .card-actions > .offer-button,
  .game-card.is-dense-v2 .card-actions > .offer-button {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    min-width: 0 !important;
    min-height: 29px !important;
    height: 29px !important;
    margin: 0 !important;
    padding: 4px !important;
    border-radius: 8px !important;
    font-size: 9.2px !important;
    line-height: 1.05 !important;
    white-space: nowrap !important;
  }

  html.poigame-index-compact .game-card.is-dense-v2 .referral-strip,
  .game-card.is-dense-v2 .referral-strip {
    grid-column: 1 / -1 !important;
    grid-row: 7 !important;
    display: grid !important;
    grid-template-columns: 1.45fr 1fr !important;
    gap: 4px !important;
    margin: 4px 0 0 !important;
  }

  html.poigame-index-compact .game-card.is-dense-v2 .referral-strip.no-code,
  .game-card.is-dense-v2 .referral-strip.no-code {
    grid-template-columns: 1fr !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-button,
  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-code,
  .game-card.is-dense-v2 .referral-strip .referral-button,
  .game-card.is-dense-v2 .referral-strip .referral-code {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    min-width: 0 !important;
    min-height: 23px !important;
    height: 23px !important;
    margin: 0 !important;
    padding: 3px 6px !important;
    border-radius: 7px !important;
    font-size: 8.2px !important;
    line-height: 1 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-button,
  .game-card.is-dense-v2 .referral-strip .referral-button {
    border: 1px solid #7047ff !important;
    background: #fff !important;
    color: #5d34da !important;
    font-weight: 900 !important;
    text-decoration: none !important;
  }

  html.poigame-index-compact body .game-card.is-dense-v2 .referral-strip .referral-code,
  .game-card.is-dense-v2 .referral-strip .referral-code {
    border: 1px solid #eee9fe !important;
    background: #faf8ff !important;
    color: #746d80 !important;
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
    if (actions && offer && !actions.contains(offer)) actions.appendChild(offer);

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
    strip.classList.toggle("no-code", !referralCode);
  };

  const scan = (root = document) => root.querySelectorAll?.(".game-card").forEach(fixCard);

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

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
</script>
'''.strip()


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"missing target: {TARGET}")

    html = TARGET.read_text(encoding="utf-8")
    if MARKER in html:
        print("compact index actions patch already present")
        return 0
    if "</body>" not in html:
        raise SystemExit("index.html missing </body>")

    TARGET.write_text(html.replace("</body>", f"{PATCH}\n</body>", 1), encoding="utf-8")
    print("patched compact index actions into _site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
