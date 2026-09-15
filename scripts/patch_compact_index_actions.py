#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGET = Path("_site/index.html")
MARKER = "POIGAME_COMPACT_ACTIONS_V4"

OLD_ACTIONS = r'''
    <div class="card-actions">
      <a href="game.html?game=${encodeURIComponent(game.name)}#comparison" class="card-action">
        比較を見る
      </a>
      ${guideHref
        ? `<a href="${guideHref}" class="card-action card-action--guide">攻略を見る</a>`
        : `<span class="card-action is-disabled">攻略準備中</span>`
      }
    </div>

    ${
      bestOffer && bestOffer.url
        ? `
          <a
            href="${POIGAME_DATA.safeHttpUrl(bestOffer.url)}"
            class="offer-button"
            target="_blank"
            rel="noopener noreferrer"
          >
            💰 最高還元サイトへ
          </a>
        `
        : `
          <span class="offer-button disabled">
            💰 案件リンク準備中
          </span>
        `
    }

    ${safeReferralUrl
      ? `
        <a
          href="${safeReferralUrl}"
          class="referral-button"
          target="_blank"
          rel="sponsored noopener noreferrer"
        >
          このポイントサイトに登録［PR］
        </a>
        <small class="referral-code">紹介コード：${POIGAME_DATA.escapeHtml(referral.code)}</small>
      `
      : ""
    }
'''.strip()

NEW_ACTIONS = r'''
    <div class="card-actions">
      <a href="game.html?game=${encodeURIComponent(game.name)}#comparison" class="card-action">
        比較を見る
      </a>
      ${guideHref
        ? `<a href="${guideHref}" class="card-action card-action--guide">攻略を見る</a>`
        : `<span class="card-action is-disabled">攻略準備中</span>`
      }
      ${
        bestOffer && bestOffer.url
          ? `
            <a
              href="${POIGAME_DATA.safeHttpUrl(bestOffer.url)}"
              class="offer-button"
              target="_blank"
              rel="noopener noreferrer"
            >
              💰 最高還元サイトへ
            </a>
          `
          : `
            <span class="offer-button disabled">
              💰 案件リンク準備中
            </span>
          `
      }
    </div>

    ${safeReferralUrl
      ? `
        <div class="referral-strip${referral.code ? "" : " no-code"}">
          <a
            href="${safeReferralUrl}"
            class="referral-button"
            target="_blank"
            rel="sponsored noopener noreferrer"
          >
            このサイトに登録［PR］
          </a>
          ${referral.code
            ? `<small class="referral-code">紹介コード：${POIGAME_DATA.escapeHtml(referral.code)}</small>`
            : ""
          }
        </div>
      `
      : ""
    }
'''.strip()

PATCH = r'''
<!-- POIGAME_COMPACT_ACTIONS_V4 -->
<style id="poigame-compact-actions-v4">
@media (max-width: 800px) {
  html.poigame-index-compact .game-card.is-dense-v2 .card-actions,
  .game-card.is-dense-v2 .card-actions {
    display: grid !important;
    grid-template-columns: .9fr .9fr 1.35fr !important;
    gap: 5px !important;
    margin-top: 5px !important;
  }

  html.poigame-index-compact .game-card.is-dense-v2 .card-actions > .card-action,
  html.poigame-index-compact .game-card.is-dense-v2 .card-actions > .offer-button,
  .game-card.is-dense-v2 .card-actions > .card-action,
  .game-card.is-dense-v2 .card-actions > .offer-button {
    min-width: 0 !important;
    min-height: 29px !important;
    height: 29px !important;
    margin: 0 !important;
    padding: 4px !important;
    border-radius: 8px !important;
    font-size: 9.2px !important;
    line-height: 1.05 !important;
    white-space: nowrap !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
  }

  html.poigame-index-compact .game-card.is-dense-v2 .card-actions > .offer-button,
  .game-card.is-dense-v2 .card-actions > .offer-button {
    background: linear-gradient(145deg,#ffe56a,#ffd23f) !important;
    color: #33165e !important;
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
'''.strip()


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"missing target: {TARGET}")

    html = TARGET.read_text(encoding="utf-8")

    if OLD_ACTIONS in html:
        html = html.replace(OLD_ACTIONS, NEW_ACTIONS, 1)
        print("rewrote card template to native three-column actions")
    elif NEW_ACTIONS in html:
        print("three-column card template already present")
    else:
        raise SystemExit("card action template not found; refusing partial patch")

    if MARKER not in html:
        if "</body>" not in html:
            raise SystemExit("index.html missing </body>")
        html = html.replace("</body>", f"{PATCH}\n</body>", 1)

    TARGET.write_text(html, encoding="utf-8")
    print("patched compact actions into _site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
