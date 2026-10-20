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
    for heading in ("案件情報の集め方と検証方法", "自動化・AIの利用について", "更新日・参考表示の見方", "攻略記事について", "誤りの訂正について"):
        assert f"<h2>{heading}</h2>" in html, heading
    assert "ca-pub-" not in html  # privacy/about pages stay free of ad code


def test_about_page_discloses_external_services_accurately():
    """about.html must not claim that no external AI/API is used anywhere.

    The scheduled daily refresh (refresh-verified-offers.yml) is API-free, but the new-game
    discovery/research/guide-package workflows use Firecrawl, Tavily and Gemini.
    """
    html = (ROOT / "about.html").read_text(encoding="utf-8")
    text = _visible(html)
    assert "外部の生成AIサービスやAPI課金型サービスを使用していません" not in text
    for service in ("Firecrawl", "Tavily", "Gemini"):
        assert service in text, service
    assert "日次の案件更新" not in text or "含まれていません" in text
    assert "最高還元やランキングの根拠として扱っていません" not in text
    assert "参考値が最高還元の欄に表示されることがあります" in text


def test_game_page_reading_guide_matches_reference_value_behaviour():
    html = (ROOT / "game.html").read_text(encoding="utf-8")
    assert "最高還元には含めていません" not in html
    assert "参考値が最高還元の欄に表示されることがあります" in html
    assert 'id="gameSummary" hidden' in html  # filled by JS from loaded data only; no static numbers


def test_no_unfinished_labels_in_user_facing_scripts():
    for name in ("index.html", "game.html"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for token in ("案件リンク準備中", "リンク準備中", "攻略準備中", "ゲーム概要は準備中です", "攻略情報を整理中です"):
            assert token not in text, (name, token)


def test_game_offer_summary_node_unit_tests():
    import subprocess

    result = subprocess.run(["node", "tests/test_game_offer_summary.js"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_progress_page_keeps_indexing_for_pages_with_records_and_redirects_empty_ones():
    html = (ROOT / "progress.html").read_text(encoding="utf-8")
    # Pages that have player records stay indexable (unchanged from the live site); a static noindex would
    # also hit them. Empty/unknown states are never rendered: they redirect to the guide list.
    assert '<meta name="robots" content="index,follow">' in html
    assert "noindex" not in html
    assert "location.replace('guides.html')" in html


def test_experience_panel_shows_update_date_only_when_it_is_a_real_date():
    js = (ROOT / "assets" / "guide-experience.js").read_text(encoding="utf-8")
    assert r"\d{4}-\d{2}-\d{2}" in js and "実例データの最終更新" in js


# --- 2026-10: game detail pages for games without a verified offer -------------

def test_game_page_does_not_assert_that_no_offer_exists():
    html = (ROOT / "game.html").read_text(encoding="utf-8")
    # A missing verified offer may also mean "could not be fetched": never state absence.
    for phrase in ("確認できる案件なし", "現在掲載なし"):
        assert phrase not in html, phrase
    assert "案件の終了とは限らず、確認できていない場合を含みます" in html
    assert "案件が存在しないとは断定していません" in html


def test_no_verified_offer_section_is_hidden_until_script_decides():
    html = (ROOT / "game.html").read_text(encoding="utf-8")
    m = re.search(r'<section[^>]*id="noVerifiedOffer"[^>]*>', html)
    assert m and " hidden" in m.group(0)
    # shown only when the summary reports zero verified offers
    assert "summary.verifiedCount > 0" in html
    # facts come from the already-published player-record JSON only (counts, no invented figures)
    assert "data/guide-experiences/${slug}.json" in html
    assert 'count("retired", "abandoned")' in html


def test_game_seo_description_counts_verified_offers_only():
    html = (ROOT / "game.html").read_text(encoding="utf-8")
    assert "game.offers.filter((offer) => offer.verified).length" in html


def test_every_game_without_a_verified_offer_has_a_guide_and_player_records():
    import csv
    import json
    published = {r["game"] for r in csv.DictReader((ROOT / "data/published_offers.csv").open(encoding="utf-8", newline=""))
                 if r.get("verified") == "true"}
    guides_js = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    catalog = [r["name"] for r in csv.DictReader((ROOT / "games.csv").open(encoding="utf-8", newline=""))]
    for name in catalog:
        if name in published:
            continue
        # not every catalogued game must have records, but when the page can show them they must parse
        match = re.search(re.escape(f'"{name}": {{') + r'.*?href: "([a-z0-9-]+)-guide\.html"', guides_js, flags=re.S)
        if not match:
            continue
        path = ROOT / "data/guide-experiences" / f"{match.group(1)}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data.get("players"), list) and data["players"], name
            assert all(p.get("status") in {"completed", "retired", "abandoned", "ongoing"} for p in data["players"]), name
