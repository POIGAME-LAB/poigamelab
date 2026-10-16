"""AdSense quality pass: first-HTML content must be meaningful before JavaScript runs.

Guards against user-visible placeholders (読み込み中 / --- 円 / 調査中) in the first HTML of
index, offers and game pages, and against reward figures being invented at build time.
"""
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from scripts.inject_static_index_fallback import inject_offers_fallback, inject_static_fallback

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = ("読み込み中", "--- 円", "-- 件", "-- 円", "----", "攻略準備中", "画像準備中")


def _visible(html: str) -> str:
    body = html[html.find("<body"):]
    return re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)


def _build(tmp_path):
    site = tmp_path / "_site"
    site.mkdir()
    for name in ("index.html", "offers.html", "games.csv"):
        (site / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    inject_static_fallback(site / "index.html", site / "games.csv")
    inject_offers_fallback(site / "offers.html", site / "games.csv")
    return site


def test_built_index_and_offers_first_html_have_no_placeholders(tmp_path):
    site = _build(tmp_path)
    for name in ("index.html", "offers.html"):
        text = _visible((site / name).read_text(encoding="utf-8"))
        for token in PLACEHOLDERS:
            assert token not in text, f"{name}: {token}"


def test_offers_fallback_lists_every_catalog_game_without_reward_figures(tmp_path):
    site = _build(tmp_path)
    html = (site / "offers.html").read_text(encoding="utf-8")
    games_csv = (ROOT / "games.csv").read_text(encoding="utf-8-sig")
    import csv
    import io
    names = [r["name"].strip() for r in csv.DictReader(io.StringIO(games_csv)) if r["name"].strip()]
    assert html.count('data-static-fallback="1"') == len(names)
    assert f'<div id="offerCount" class="count">{len(names)} 件</div>' in html
    for name in names:
        assert escape(name) in html, name
        assert f"game.html?game={quote(name, safe='')}" in html, name
    # rewards come only from verified data rendered by JavaScript; never from the build step
    assert "最高還元" not in html.split("OFFERS_FALLBACK_V1")[1].split("</section>")[0]
    assert not re.search(r"\d{1,3}(,\d{3})*\s*円", html.split("OFFERS_FALLBACK_V1")[1].split("</section>")[0])
    assert "grid.replaceChildren();" in html  # JS replaces static cards, no duplicates


def test_offers_fallback_is_idempotent_and_refuses_empty_catalog(tmp_path):
    site = _build(tmp_path)
    first = (site / "offers.html").read_text(encoding="utf-8")
    assert inject_offers_fallback(site / "offers.html", site / "games.csv") == {"alreadyPatched": True}
    assert (site / "offers.html").read_text(encoding="utf-8") == first

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "offers.html").write_text((ROOT / "offers.html").read_text(encoding="utf-8"), encoding="utf-8")
    (empty / "games.csv").write_text("name,image,condition\n", encoding="utf-8")
    try:
        inject_offers_fallback(empty / "offers.html", empty / "games.csv")
    except RuntimeError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("empty catalog must not be published")
    assert 'data-static-fallback="1"' not in (empty / "offers.html").read_text(encoding="utf-8")


def test_game_page_first_html_is_not_placeholder_text_and_explains_the_table():
    html = (ROOT / "game.html").read_text(encoding="utf-8")
    text = _visible(html)
    for token in ("読み込み中", "--- 円", "ゲーム名", "調査中</p>"):
        assert token not in text, token
    assert 'id="how-to-read"' in html
    assert "（参考）" in text and "［PR］" in text
    # per-game SEO is applied once the game is known; unknown games are not indexable
    assert 'rel: "canonical"' in html and "applyGameSeo(game)" in html
    assert 'name: "robots", content: "noindex"' in html


def test_index_dynamic_cards_do_not_show_dash_placeholders():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert '"--- 円"' not in html
    assert "おすすめポイントサイト：" in html and "確認済みの案件データはまだありません" in html


def test_about_page_explains_data_method_and_reading_rules():
    html = (ROOT / "about.html").read_text(encoding="utf-8")
    for heading in ("案件情報の集め方と検証方法", "更新日・参考表示の見方", "攻略記事について", "誤りの訂正について"):
        assert f"<h2>{heading}</h2>" in html, heading
    assert "ca-pub-" not in html  # privacy/about pages stay free of ad code
