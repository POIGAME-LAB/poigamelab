#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

TARGET = Path("_site/index.html")
GAMES_CSV = Path("_site/games.csv")
MARKER = "POIGAME_STATIC_INDEX_FALLBACK_V1"


def _read_games(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if str(row.get("name") or "").strip()]
    rows.sort(key=lambda row: str(row.get("featured") or "").strip().lower() != "true")
    return rows


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


def _build_cards(games: list[dict[str, str]]) -> str:
    cards: list[str] = []
    for index, game in enumerate(games):
        name = str(game.get("name") or "").strip()
        condition = str(game.get("condition") or "").strip() or "指定条件クリア"
        days = str(game.get("days") or "").strip() or "調査中"
        difficulty = str(game.get("difficulty") or "").strip() or "調査中"
        featured = str(game.get("featured") or "").strip().lower() == "true"
        image = _thumbnail_path(game.get("image"))
        detail_href = f"game.html?game={quote(name, safe='')}"

        if image:
            image_markup = (
                f'<img class="game-thumbnail" src="{escape(image, quote=True)}" '
                f'alt="{escape(name, quote=True)} イメージ" loading="lazy">'
            )
        else:
            image_markup = (
                f'<div class="image-placeholder"><small>POIGAME LAB</small>'
                f'<strong>{escape(name)}</strong></div>'
            )

        if index < 3:
            badge = f'<span class="rank-badge">{index + 1}位</span>'
        elif featured:
            badge = '<span class="rank-badge">注目</span>'
        else:
            badge = ""

        cards.append(
            f'''<article class="game-card" data-static-fallback="1">
  <div class="game-image">{image_markup}</div>
  <div class="game-info">
    <div class="card-rank-row">{badge}</div>
    <h3><a class="game-title-link" href="{detail_href}">{escape(name)}</a></h3>
    <p class="game-condition">{escape(condition)}</p>
    <div class="reward-box"><span>最高還元</span><strong>確認中</strong></div>
    <p class="point-site">最新案件データを読み込み中</p>
    <div class="game-meta">
      <span>⏱ 達成目安：{escape(days)}</span>
      <span>🎮 難易度：{escape(difficulty)}</span>
    </div>
    <div class="card-actions">
      <a href="{detail_href}#comparison" class="card-action">比較を見る</a>
      <a href="{detail_href}" class="card-action card-action--guide">詳細を見る</a>
    </div>
  </div>
</article>'''
        )
    return "\n".join(cards)


def inject_static_fallback(index_path: Path = TARGET, games_path: Path = GAMES_CSV) -> dict[str, object]:
    if not index_path.exists():
        raise RuntimeError(f"missing target: {index_path}")
    if not games_path.exists():
        raise RuntimeError(f"missing games CSV: {games_path}")

    html = index_path.read_text(encoding="utf-8")
    if MARKER in html:
        required = (
            'data-static-fallback="1"',
            "let catalogLoaded = false;",
            "catalogLoaded = true;",
            'if (!catalogLoaded && gameGrid.querySelector(\'[data-static-fallback="1"]\'))',
        )
        if not all(token in html for token in required):
            raise RuntimeError("static fallback marker exists but protective patch is incomplete")
        return {"alreadyPatched": True}

    games = _read_games(games_path)
    if not games:
        raise RuntimeError("refusing to publish an empty static game fallback")
    cards = _build_cards(games)

    grid_pattern = re.compile(r'(<div class="game-grid">)\s*(</div>)', flags=re.DOTALL)
    html, count = grid_pattern.subn(
        lambda match: f'{match.group(1)}\n<!-- {MARKER} -->\n{cards}\n          {match.group(2)}',
        html,
        count=1,
    )
    if count != 1:
        raise RuntimeError("expected exactly one empty .game-grid in built index.html")

    count_placeholder = '<strong id="statGameCount">-- 件</strong>'
    if count_placeholder not in html:
        raise RuntimeError("game-count dashboard placeholder changed unexpectedly")
    html = html.replace(
        count_placeholder,
        f'<strong id="statGameCount">{len(games)} 件</strong>',
        1,
    )

    declaration = '  let currentSort = "recommended";\n  let currentSearch = "";'
    if declaration not in html:
        raise RuntimeError("index state declaration changed unexpectedly")
    html = html.replace(declaration, declaration + '\n  let catalogLoaded = false;', 1)

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
    return {"alreadyPatched": False, "gameCount": len(games)}


def main() -> int:
    summary = inject_static_fallback()
    if summary.get("alreadyPatched"):
        print("static index fallback already present")
    else:
        print(f"injected static index fallback: games={summary['gameCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
