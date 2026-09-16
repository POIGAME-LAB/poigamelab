#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

TARGET = Path("_site/index.html")
GAMES_CSV = Path("_site/games.csv")
OFFERS_CSV = Path("_site/data/published_offers.csv")
MARKER = "POIGAME_STATIC_INDEX_FALLBACK_V1"

POINT_SITES = {
    "moppy": "モッピー",
    "warau": "ワラウ",
    "chobirich": "ちょびリッチ",
    "coincome": "COINCOME",
    "mikoshi": "MIKOSHI",
    "pointtown": "ポイントタウン",
    "hapitas": "ハピタス",
    "ecnav": "ECナビ",
    "pointincome": "ポイントインカム",
    "getmoney": "GetMoney!",
    "itsmon": "itsmon",
    "poney": "PONEY",
    "rakuten": "楽天リーベイツ",
    "mercari": "メルカリ",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_true(value: object) -> bool:
    return str(value or "").strip().lower() == "true"


def _reward(value: object) -> int:
    try:
        return max(0, int(float(str(value or "0").replace(",", ""))))
    except (TypeError, ValueError):
        return 0


def _thumbnail_path(raw_value: object) -> str:
    raw = str(raw_value or "").strip()
    if not raw.startswith("assets/game-art/"):
        return raw

    filename = raw.split("?", 1)[0].rsplit("/", 1)[-1]
    if not re.search(r"(?:\.(?:png|jpe?g))+$", filename, flags=re.IGNORECASE):
        return raw

    stem = filename
    while re.search(r"\.(?:png|jpe?g)$", stem, flags=re.IGNORECASE):
        stem = re.sub(r"\.(?:png|jpe?g)$", "", stem, flags=re.IGNORECASE)
    return f"assets/game-thumbs/{stem.lower()}.jpg"


def _best_offer_by_game(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    best: dict[str, dict[str, object]] = {}
    for row in rows:
        if not _is_true(row.get("verified")):
            continue
        game = str(row.get("game") or "").strip()
        reward = _reward(row.get("reward"))
        if not game or reward <= 0:
            continue
        current = best.get(game)
        if current is None or reward > int(current["reward"]):
            best[game] = {
                "reward": reward,
                "site": str(row.get("site") or "").strip(),
                "updatedAt": str(row.get("updatedAt") or "").strip(),
                "verified": True,
            }
    return best


def _catalog_offer(game: dict[str, str], verified: dict[str, object] | None) -> dict[str, object] | None:
    if verified is not None:
        return verified
    reward = _reward(game.get("provisionalReward"))
    if reward <= 0:
        return None
    return {
        "reward": reward,
        "site": str(game.get("provisionalSource") or "").strip(),
        "updatedAt": str(game.get("addedDate") or "").strip(),
        "verified": False,
    }


def _site_label(raw_site: object) -> str:
    raw = str(raw_site or "").strip()
    if not raw:
        return "調査中"
    return POINT_SITES.get(raw.lower(), POINT_SITES.get(raw, raw))


def _build_cards(games: list[dict[str, str]], offers: dict[str, dict[str, object]]) -> tuple[str, int, str]:
    ordered = list(enumerate(games))
    ordered.sort(key=lambda pair: (not _is_true(pair[1].get("featured")), pair[0]))

    cards: list[str] = []
    max_reward = 0
    latest_update = ""

    for card_index, (_, game) in enumerate(ordered):
        name = str(game.get("name") or "").strip()
        if not name:
            continue

        condition = str(game.get("condition") or "").strip() or "指定条件クリア"
        days = str(game.get("days") or "").strip() or "調査中"
        difficulty = str(game.get("difficulty") or "").strip() or "調査中"
        image = _thumbnail_path(game.get("image"))
        offer = _catalog_offer(game, offers.get(name))
        detail_href = f"game.html?game={quote(name, safe='')}"

        if offer:
            reward = int(offer["reward"])
            max_reward = max(max_reward, reward)
            updated_at = str(offer.get("updatedAt") or "")
            latest_update = max(latest_update, updated_at)
            reward_text = f"{reward:,} 円"
            site_text = _site_label(offer.get("site"))
            verification_class = "verified" if offer.get("verified") else "legacy"
            verification_text = "掲載確認済み" if offer.get("verified") else "参考掲載"
        else:
            reward_text = "確認中"
            site_text = "調査中"
            verification_class = "legacy"
            verification_text = "案件情報を確認中"

        image_markup = (
            f'<img class="game-thumbnail" src="{escape(image, quote=True)}" '
            f'alt="{escape(name, quote=True)} イメージ" loading="lazy">'
            if image
            else f'<div class="image-placeholder"><small>POIGAME LAB</small><strong>{escape(name)}</strong></div>'
        )
        badge = f'<span class="rank-badge">{card_index + 1}位</span>' if card_index < 3 else (
            '<span class="rank-badge">注目</span>' if _is_true(game.get("featured")) else ""
        )

        cards.append(
            f'''<article class="game-card" data-static-fallback="1">
  <div class="game-image">{image_markup}</div>
  <div class="game-info">
    <div class="card-rank-row">{badge}</div>
    <h3><a class="game-title-link" href="{detail_href}">{escape(name)}</a></h3>
    <p class="game-condition">{escape(condition)}</p>
    <div class="reward-box"><span>最高還元</span><strong>{escape(reward_text)}</strong></div>
    <p class="point-site">おすすめポイントサイト：{escape(site_text)}</p>
    <p class="verification-line {verification_class}">{escape(verification_text)}</p>
    <div class="game-meta">
      <span>⏱ 達成目安：{escape(days)}</span>
      <span>🎮 難易度：{escape(difficulty)}</span>
    </div>
    <div class="card-actions">
      <a href="{detail_href}#comparison" class="card-action">比較を見る</a>
      <a href="{detail_href}" class="card-action card-action--guide">詳細を見る</a>
    </div>
    <span class="offer-button disabled">案件リンク読み込み中</span>
  </div>
</article>'''
        )

    return "\n".join(cards), max_reward, latest_update


def inject_static_fallback(index_path: Path = TARGET, games_path: Path = GAMES_CSV, offers_path: Path = OFFERS_CSV) -> dict[str, object]:
    if not index_path.exists():
        raise RuntimeError(f"missing target: {index_path}")
    if not games_path.exists():
        raise RuntimeError(f"missing games CSV: {games_path}")
    if not offers_path.exists():
        raise RuntimeError(f"missing published offers CSV: {offers_path}")

    html = index_path.read_text(encoding="utf-8")
    if MARKER in html:
        required = (
            'data-static-fallback="1"',
            "let catalogLoaded = false;",
            "catalogLoaded = true;",
            "if (!catalogLoaded && gameGrid.querySelector('[data-static-fallback=\"1\"]'))",
        )
        if not all(token in html for token in required):
            raise RuntimeError("static fallback marker exists but protective patch is incomplete")
        return {"alreadyPatched": True}

    games = _read_csv(games_path)
    verified_offers = _best_offer_by_game(_read_csv(offers_path))
    cards, max_reward, latest_update = _build_cards(games, verified_offers)
    game_count = sum(1 for row in games if str(row.get("name") or "").strip())
    if game_count <= 0 or not cards:
        raise RuntimeError("refusing to publish an empty static game fallback")

    grid_pattern = re.compile(r'(<div class="game-grid">)\s*(</div>)', flags=re.DOTALL)
    replacement = rf'''\1
<!-- {MARKER} -->
{cards}
          \2'''
    html, count = grid_pattern.subn(replacement, html, count=1)
    if count != 1:
        raise RuntimeError("expected exactly one empty .game-grid in built index.html")

    dashboard_replacements = {
        '<strong id="statGameCount">-- 件</strong>': f'<strong id="statGameCount">{game_count} 件</strong>',
        '<strong id="statMaxReward">-- 円</strong>': (
            f'<strong id="statMaxReward">{max_reward:,} 円</strong>' if max_reward else '<strong id="statMaxReward">確認待ち</strong>'
        ),
        '<strong id="statUpdated">----</strong>': f'<strong id="statUpdated">{escape(latest_update[:10] or "確認待ち")}</strong>',
    }
    for old, new in dashboard_replacements.items():
        if old not in html:
            raise RuntimeError(f"dashboard placeholder changed unexpectedly: {old}")
        html = html.replace(old, new, 1)

    declaration = '  let currentSort = "recommended";\n  let currentSearch = "";'
    if declaration not in html:
        raise RuntimeError("index state declaration changed unexpectedly")
    html = html.replace(
        declaration,
        declaration + '\n  let catalogLoaded = false;',
        1,
    )

    load_marker = '      const rows = await POIGAME_DATA.fetchCsv("games.csv");\n      games.length = 0;'
    if load_marker not in html:
        raise RuntimeError("loadGames structure changed unexpectedly")
    html = html.replace(
        load_marker,
        '      const rows = await POIGAME_DATA.fetchCsv("games.csv");\n      catalogLoaded = true;\n      games.length = 0;',
        1,
    )

    render_marker = '  function renderGames() {\n    updateDashboard();'
    if render_marker not in html:
        raise RuntimeError("renderGames structure changed unexpectedly")
    html = html.replace(
        render_marker,
        '  function renderGames() {\n'
        '    if (!catalogLoaded && gameGrid.querySelector(\'[data-static-fallback="1"]\')) {\n'
        '      return;\n'
        '    }\n'
        '    updateDashboard();',
        1,
    )

    index_path.write_text(html, encoding="utf-8")
    return {
        "alreadyPatched": False,
        "gameCount": game_count,
        "maxReward": max_reward,
        "latestUpdate": latest_update,
    }


def main() -> int:
    summary = inject_static_fallback()
    if summary.get("alreadyPatched"):
        print("static index fallback already present")
    else:
        print(
            "injected static index fallback: "
            f"games={summary['gameCount']} max_reward={summary['maxReward']} updated={summary['latestUpdate'] or 'n/a'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
