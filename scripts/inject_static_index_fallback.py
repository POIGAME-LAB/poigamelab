#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

TARGET = Path("_site/index.html")
OFFERS_TARGET = Path("_site/offers.html")
GAMES_CSV = Path("_site/games.csv")
MARKER = "POIGAME_STATIC_INDEX_FALLBACK_V1"
OFFERS_MARKER = "POIGAME_STATIC_OFFERS_FALLBACK_V1"

# Same thresholds as site-data.js (OFFER_OLD_DAYS): a verified row confirmed
# within this many days may lead a card; older rows are shown with their age.
OFFER_OLD_DAYS = 30
JST = timezone(timedelta(hours=9))
SITE_LABELS = {
    "moppy": "モッピー", "warau": "ワラウ", "chobirich": "ちょびリッチ", "coincome": "COINCOME",
    "mikoshi": "MIKOSHI", "gendama": "げん玉", "amefuri": "アメフリ", "point_town": "ポイントタウン",
    "pointtown": "ポイントタウン", "hapitas": "ハピタス", "ec_navi": "ECナビ", "ecnavi": "ECナビ",
    "point_income": "ポイントインカム", "pointincome": "ポイントインカム",
}


def _today_jst() -> date:
    return datetime.now(JST).date()


def _parse_day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _read_verified_offers(path: Path | None) -> list[dict[str, object]] | None:
    """Verified rows from the published CSV, or None when the file is absent.

    None means "unknown" (no figures are baked in); an empty list means the
    file was read and holds no verified offer.
    """
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    offers: list[dict[str, object]] = []
    for row in rows:
        try:
            reward = int(str(row.get("reward") or "0").strip())
        except ValueError:
            continue
        if str(row.get("verified") or "").strip().lower() != "true" or reward <= 0:
            continue
        game = str(row.get("game") or "").strip()
        if not game:
            continue
        offers.append({
            "game": game,
            "site": str(row.get("site") or "").strip(),
            "reward": reward,
            "platform": str(row.get("platform") or "").strip(),
            "updatedAt": str(row.get("updatedAt") or "").strip(),
        })
    return offers


def _age_days(offer: dict[str, object], today: date) -> int | None:
    day = _parse_day(offer.get("updatedAt"))
    return None if day is None else max(0, (today - day).days)


def _headline(offers: list[dict[str, object]], today: date) -> dict[str, object] | None:
    if not offers:
        return None
    recent = [o for o in offers if (_age_days(o, today) is not None and _age_days(o, today) <= OFFER_OLD_DAYS)]
    pool = recent or offers
    return max(pool, key=lambda o: int(o["reward"]))


def _short_day(value: object) -> str:
    day = _parse_day(value)
    return f"{day.month}/{day.day}" if day else ""


def _confirmation_text(offer: dict[str, object], today: date) -> str:
    days = _age_days(offer, today)
    if days is None:
        return "確認日の記録なし"
    if days > OFFER_OLD_DAYS:
        return f"最終確認 {_short_day(offer['updatedAt'])}（{days}日前）"
    return f"{_short_day(offer['updatedAt'])}確認"


def _site_label(site: object) -> str:
    return SITE_LABELS.get(str(site or ""), str(site or ""))


def _offers_by_game(offers: list[dict[str, object]] | None) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for offer in offers or []:
        grouped.setdefault(str(offer["game"]), []).append(offer)
    return grouped


def _read_games(path: Path, verified_games: set[str] | None = None) -> list[dict[str, str]]:
    """Catalog rows in the same order the page script uses: games that have a
    verified offer first, then the editorial "featured" flag, then CSV order."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if str(row.get("name") or "").strip()]
    has_offer = verified_games or set()
    rows.sort(key=lambda row: (
        str(row.get("name") or "").strip() not in has_offer,
        str(row.get("featured") or "").strip().lower() != "true",
    ))
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


def _overview_excerpt(game: dict[str, str], limit: int = 90) -> str:
    """First sentence of the catalog overview (games.csv), trimmed for a card."""
    text = str(game.get("overview") or "").strip()
    if not text:
        return ""
    sentence = text.split("。")[0].strip()
    if len(sentence) > limit:
        sentence = sentence[: limit - 1].rstrip() + "…"
    return sentence


def _reward_markup(
    offers: list[dict[str, object]] | None, today: date
) -> tuple[str, str]:
    """(reward box text, site/age line) for one game, from verified rows only."""
    if offers is None:
        return "詳細で比較", ""
    best = _headline(offers, today)
    if best is None:
        return "確認済み案件なし", "確認済みの案件は現在掲載していません（終了とは限りません）"
    return (
        f"{int(best['reward']):,} 円",
        f"最高還元のサイト：{_site_label(best['site'])}（{_confirmation_text(best, today)}）",
    )


def _build_cards(
    games: list[dict[str, str]],
    offers_by_game: dict[str, list[dict[str, object]]] | None = None,
    today: date | None = None,
) -> str:
    today = today or _today_jst()
    cards: list[str] = []
    for index, game in enumerate(games):
        name = str(game.get("name") or "").strip()
        condition = str(game.get("condition") or "").strip() or "指定条件クリア"
        days = str(game.get("days") or "").strip() or "調査中"
        difficulty = str(game.get("difficulty") or "").strip() or "調査中"
        featured = str(game.get("featured") or "").strip().lower() == "true"
        overview_markup = escape(_overview_excerpt(game)) or "ポイントサイト別の還元額と条件を比較できます"
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

        # No numbered rank here: the default order is not a measured ranking.
        badge = '<span class="rank-badge">注目</span>' if featured else ""
        game_offers = None if offers_by_game is None else offers_by_game.get(name, [])
        reward_text, site_line = _reward_markup(game_offers, today)
        point_site_markup = escape(site_line) if site_line else overview_markup

        cards.append(
            f'''<article class="game-card" data-static-fallback="1">
  <div class="game-image">{image_markup}</div>
  <div class="game-info">
    <div class="card-rank-row">{badge}</div>
    <h3><a class="game-title-link" href="{detail_href}">{escape(name)}</a></h3>
    <p class="game-condition">{escape(condition)}</p>
    <div class="reward-box"><span>最高還元</span><strong>{escape(reward_text)}</strong></div>
    <p class="point-site">{point_site_markup}</p>
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


def _dashboard_values(
    offers: list[dict[str, object]] | None, today: date
) -> tuple[str, str, str, str] | None:
    """(max reward, its note, latest confirmation date, run note) or None."""
    if offers is None:
        return None
    if not offers:
        return ("現在、確認済み案件の掲載はありません", "", "—", "")
    best = _headline(offers, today)
    days = [d for d in (_parse_day(o.get("updatedAt")) for o in offers) if d]
    latest = max(days).strftime("%Y/%m/%d") if days else "—"
    old = sum(1 for o in offers if (_age_days(o, today) or 0) > OFFER_OLD_DAYS)
    note = f"{_site_label(best['site'])}・{_confirmation_text(best, today)}"
    run_note = f"{old}件は確認から{OFFER_OLD_DAYS}日以上" if old else ""
    return (f"{int(best['reward']):,} 円", note, latest, run_note)


def inject_static_fallback(
    index_path: Path = TARGET,
    games_path: Path = GAMES_CSV,
    published_path: Path | None = None,
    today: date | None = None,
) -> dict[str, object]:
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

    today = today or _today_jst()
    if published_path is None:
        # The published CSV shipped in the same artifact as games.csv.
        published_path = games_path.parent / "data" / "published_offers.csv"
    verified = _read_verified_offers(published_path)
    grouped = None if verified is None else _offers_by_game(verified)
    games = _read_games(games_path, set(grouped or {}))
    if not games:
        raise RuntimeError("refusing to publish an empty static game fallback")
    cards = _build_cards(games, grouped, today)

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

    # Bake the verified figures into the first HTML so the dashboard never shows
    # an empty or "確認中" value before (or without) JavaScript. The page script
    # replaces them with the freshly downloaded data and keeps them on failure.
    dashboard = _dashboard_values(verified, today)
    if dashboard is not None:
        max_reward, max_note, latest, run_note = dashboard
        message = ' class="is-message"' if not verified else ""
        for marker, value, extra in (
            ('<strong id="statMaxReward" aria-live="polite"></strong>', max_reward, message),
            ('<strong id="statUpdated" aria-live="polite"></strong>', latest, ""),
        ):
            if marker not in html:
                raise RuntimeError(f"dashboard placeholder changed unexpectedly: {marker}")
            element_id = "statMaxReward" if "statMaxReward" in marker else "statUpdated"
            html = html.replace(
                marker,
                f'<strong id="{element_id}" aria-live="polite" data-static-value="1"{extra}>{escape(value)}</strong>',
                1,
            )
        for marker, value in (
            ('<small id="statMaxRewardNote" class="dashboard-stat-note"></small>', max_note),
            ('<small id="statRunNote" class="dashboard-stat-note"></small>', run_note),
        ):
            if marker not in html:
                raise RuntimeError(f"dashboard note placeholder changed unexpectedly: {marker}")
            element_id = "statMaxRewardNote" if "MaxReward" in marker else "statRunNote"
            html = html.replace(marker, f'<small id="{element_id}" class="dashboard-stat-note">{escape(value)}</small>', 1)

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
        '      // Catalog download failed: keep the build-time cards, but still say so.\n'
        '      updateDashboard();\n'
        '      return;\n'
        '    }\n'
        '    updateDashboard();',
        1,
    )

    index_path.write_text(html, encoding="utf-8")
    return {
        "alreadyPatched": False,
        "gameCount": len(games),
        "verifiedOfferCount": None if verified is None else len(verified),
    }


def _build_offer_cards(
    games: list[dict[str, str]],
    offers_by_game: dict[str, list[dict[str, object]]] | None = None,
    today: date | None = None,
) -> str:
    today = today or _today_jst()
    cards: list[str] = []
    for game in games:
        name = str(game.get("name") or "").strip()
        condition = str(game.get("condition") or "").strip() or "指定条件クリア"
        days = str(game.get("days") or "").strip() or "調査中"
        difficulty = str(game.get("difficulty") or "").strip() or "調査中"
        overview = str(game.get("overview") or "").strip()
        detail_href = f"game.html?game={quote(name, safe='')}"
        overview_markup = f'\n          <p class="condition">{escape(overview)}</p>' if overview else ""
        reward_markup = ""
        if offers_by_game is not None:
            game_offers = offers_by_game.get(name, [])
            reward_text, site_line = _reward_markup(game_offers, today)
            sites = sorted({_site_label(o["site"]) for o in game_offers})
            facts = (
                f'\n          <ul class="facts"><li><span>確認済み案件</span><span>{len(sites)}サイト・{len(game_offers)}件</span></li></ul>'
                if game_offers else ""
            )
            reward_markup = (
                f'\n          <div class="reward"><span>最高還元</span><strong>{escape(reward_text)}</strong></div>'
                f'\n          <p class="best-line">{escape(site_line)}</p>{facts}'
            )
        cards.append(
            f'''<article class="card" data-static-fallback="1">
        <div class="body">
          <h2><a href="{detail_href}">{escape(name)}</a></h2>
          <p class="condition">{escape(condition)}</p>{overview_markup}{reward_markup}
          <div class="meta"><span>⏱ {escape(days)}</span><span>🎮 {escape(difficulty)}</span></div>
          <div class="actions">
            <a class="compare" href="{detail_href}#comparison">比較を見る</a>
            <a class="guide" href="{detail_href}">詳細を見る</a>
          </div>
        </div>
      </article>'''
        )
    return "\n      ".join(cards)


def inject_offers_fallback(
    offers_path: Path = OFFERS_TARGET,
    games_path: Path = GAMES_CSV,
    published_path: Path | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Put the catalog into offers.html's first HTML, with the verified figures.

    Reward figures come only from verified rows of the published CSV that is
    shipped in the same artifact, each with its confirmation date; reference
    values from games.csv are never baked in. The page's own script replaces the
    grid on load (``grid.replaceChildren()``), so nothing is duplicated.
    """
    if not offers_path.exists():
        raise RuntimeError(f"missing target: {offers_path}")
    if not games_path.exists():
        raise RuntimeError(f"missing games CSV: {games_path}")

    html = offers_path.read_text(encoding="utf-8")
    if OFFERS_MARKER in html:
        return {"alreadyPatched": True}

    today = today or _today_jst()
    if published_path is None:
        # The published CSV shipped in the same artifact as games.csv.
        published_path = games_path.parent / "data" / "published_offers.csv"
    verified = _read_verified_offers(published_path)
    grouped = None if verified is None else _offers_by_game(verified)
    games = _read_games(games_path, set(grouped or {}))
    if not games:
        raise RuntimeError("refusing to publish an empty static offers fallback")

    grid = '<section id="offerGrid" class="grid" aria-live="polite"></section>'
    if html.count(grid) != 1:
        raise RuntimeError("expected exactly one empty #offerGrid in built offers.html")
    html = html.replace(
        grid,
        f'<section id="offerGrid" class="grid" aria-live="polite">\n      <!-- {OFFERS_MARKER} -->\n      '
        f'{_build_offer_cards(games, grouped, today)}\n  </section>',
        1,
    )

    count_placeholder = '<div id="offerCount" class="count">-- 件</div>'
    if count_placeholder not in html:
        raise RuntimeError("offer-count placeholder changed unexpectedly")
    html = html.replace(
        count_placeholder,
        f'<div id="offerCount" class="count">{len(games)} 件</div>',
        1,
    )

    if "grid.replaceChildren();" not in html:
        raise RuntimeError("offers.html no longer replaces the grid on render; static cards would duplicate")

    offers_path.write_text(html, encoding="utf-8")
    return {"alreadyPatched": False, "gameCount": len(games)}


def main() -> int:
    summary = inject_static_fallback()
    if summary.get("alreadyPatched"):
        print("static index fallback already present")
    else:
        print(f"injected static index fallback: games={summary['gameCount']}")
    offers_summary = inject_offers_fallback()
    if offers_summary.get("alreadyPatched"):
        print("static offers fallback already present")
    else:
        print(f"injected static offers fallback: games={offers_summary['gameCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
