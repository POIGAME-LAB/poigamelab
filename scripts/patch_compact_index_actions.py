#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGET = Path("_site/index.html")
MARKER = "POIGAME_COMPACT_ACTIONS_V5"

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
<!-- POIGAME_COMPACT_ACTIONS_V5 -->
<style id="poigame-compact-actions-v5">
@media (max-width: 800px) {
  body .game-card .card-actions {
    display: grid !important;
    grid-template-columns: minmax(0,.9fr) minmax(0,.9fr) minmax(0,1.35fr) !important;
    grid-auto-flow: column !important;
    grid-auto-columns: minmax(0,1fr) !important;
    gap: 5px !important;
    width: 100% !important;
    margin-top: 5px !important;
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

  body .game-card .card-actions > .offer-button {
    background: linear-gradient(145deg,#ffe56a,#ffd23f) !important;
    color: #33165e !important;
  }

  body .game-card .referral-strip {
    display: grid !important;
    grid-template-columns: minmax(0,1.45fr) minmax(0,1fr) !important;
    gap: 4px !important;
    width: 100% !important;
    margin: 4px 0 0 !important;
  }

  body .game-card .referral-strip.no-code {
    grid-template-columns: 1fr !important;
  }

  body .game-card .referral-strip .referral-button,
  body .game-card .referral-strip .referral-code {
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

  body .game-card .referral-strip .referral-button {
    border: 1px solid #7047ff !important;
    background: #fff !important;
    color: #5d34da !important;
    font-weight: 900 !important;
    text-decoration: none !important;
  }

  body .game-card .referral-strip .referral-code {
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

    # Remove older inline compact-action patches so V5 is the only final authority.
    for version in ("V3", "V4"):
        marker = f"<!-- POIGAME_COMPACT_ACTIONS_{version} -->"
        if marker in html:
            start = html.index(marker)
            end_style = html.find("</style>", start)
            if end_style != -1:
                html = html[:start] + html[end_style + len("</style>"):]

    if MARKER not in html:
        if "</body>" not in html:
            raise SystemExit("index.html missing </body>")
        html = html.replace("</body>", f"{PATCH}\n</body>", 1)

    TARGET.write_text(html, encoding="utf-8")
    print("patched class-independent three-column actions into _site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
