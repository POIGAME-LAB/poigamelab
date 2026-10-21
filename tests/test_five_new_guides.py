import csv
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

GUIDES = {
    "ATLAS: EARTH": "atlas-earth-guide.html",
    "ファミリーファームの冒険": "family-farm-adventure-guide.html",
    "クロンダイクの冒険": "klondike-adventures-guide.html",
    "Merge Help: ホームデザインパズル": "merge-help-guide.html",
    "マジックジグソーパズル": "magic-jigsaw-puzzles-guide.html",
}

GAME_IMAGES = {
    "ATLAS: EARTH": "assets/game-art/atlas-earth.PNG",
    "ファミリーファームの冒険": "assets/game-art/family-farm-adventure.PNG",
    "クロンダイクの冒険": "assets/game-art/klondike-adventures.PNG",
    "Merge Help: ホームデザインパズル": "assets/game-art/merge-help.PNG",
    "マジックジグソーパズル": "assets/game-art/magic-jigsaw-puzzles.PNG",
}


def test_new_guides_exist_and_disclose_research_status():
    for name, filename in GUIDES.items():
        page = (ROOT / filename).read_text(encoding="utf-8")
        assert name.split(":")[0] in page
        if name == "ATLAS: EARTH":
            assert "実際のプレイヤー記録" in page
            assert "2026年9月14日時点" in page
        elif name in {"ファミリーファームの冒険", "クロンダイクの冒険"}:
            assert "実際のプレイヤー記録" in page
            assert "調査更新：2026-09-14" in page
        elif name in {"Merge Help: ホームデザインパズル", "マジックジグソーパズル"}:
            assert "実際のプレイヤー記録" in page
            assert "調査更新：2026-09-15" in page
        assert f"https://poigamelab.com/{filename}" in page
        assert "site-header.js" in page
        assert "site-footer.js" in page


def test_catalog_registry_links_every_new_page():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    researched = (ROOT / "site-researched-guides.js").read_text(encoding="utf-8")
    for name, filename in GUIDES.items():
        assert f'"{name}"' in catalog
        assert f'href: "{filename}"' in catalog
        assert f'"{name}"' in researched


def test_guide_hub_keeps_researched_registry_available():
    hub = (ROOT / "guides.html").read_text(encoding="utf-8")
    assert '<script src="site-researched-guides.js"></script>' in hub
    assert "Object.entries(window.POIGAME_RESEARCHED_GUIDES || {})" in hub
    assert "rendered.has(name)" in hub


def test_sitemap_contains_every_new_guide():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    for filename in GUIDES.values():
        assert f"https://poigamelab.com/{filename}" in sitemap


def test_public_builder_includes_new_guides_and_registry():
    builder = (ROOT / "scripts" / "build_public_site.py").read_text(encoding="utf-8")
    for filename in GUIDES.values():
        assert f'"{filename}"' in builder
    assert '"site-researched-guides.js"' in builder


def test_all_five_are_formal_catalog_games_with_uploaded_image_and_reference_reward():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}

    for name in GUIDES:
        assert name in rows
        row = rows[name]
        assert row["image"] == GAME_IMAGES[name]
        image_path = ROOT / GAME_IMAGES[name]
        assert image_path.is_file()
        assert image_path.stat().st_size > 100_000
        assert int(row["provisionalReward"]) > 0
        assert row["provisionalSource"].strip()
        assert row["addedDate"] == "2026-09-12"


def test_atlas_catalog_has_researched_pace_instead_of_placeholder_values():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    atlas = rows["ATLAS: EARTH"]
    assert "30日StepUp" in atlas["days"]
    assert "14日で土地6個" in atlas["days"]
    assert "課金有無で差大" in atlas["difficulty"]
    assert "調査中" not in atlas["difficulty"]


def test_family_farm_catalog_has_researched_pace_instead_of_placeholder_values():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    game = rows["ファミリーファームの冒険"]
    assert "Lv26実例7〜16日" in game["days"]
    assert "Lv30実例9〜24日" in game["days"]
    assert "Lv40未達例20日Lv35" in game["days"]
    assert "Lv40は高難度" in game["difficulty"]
    assert "調査中" not in game["difficulty"]


def test_klondike_catalog_has_researched_pace_instead_of_placeholder_values():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    game = rows["クロンダイクの冒険"]
    assert "Lv20実例6〜13日" in game["days"]
    assert "Lv22実例8〜18日" in game["days"]
    assert "Lv24実例10〜12日" in game["days"]
    assert "Lv40実例約45日" in game["days"]
    assert "Lv40は高難度" in game["difficulty"]
    assert "調査中" not in game["difficulty"]


def test_merge_help_catalog_has_researched_pace_instead_of_placeholder_values():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    game = rows["Merge Help: ホームデザインパズル"]
    assert "Lv10実例4日" in game["days"]
    assert "Lv20実例11日" in game["days"]
    assert "Lv28実例22日" in game["days"]
    assert "期限30日" in game["days"]
    assert "普通〜やや難" in game["difficulty"]
    assert "調査中" not in game["difficulty"]


def test_magic_jigsaw_catalog_has_researched_pace_instead_of_placeholder_values():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    game = rows["マジックジグソーパズル"]
    assert "7,000コイン実例9日" in game["days"]
    assert "11,000コイン実例4〜7日" in game["days"]
    assert "15,000コイン期限22日" in game["days"]
    assert "広告視聴時間が必要" in game["difficulty"]
    assert "調査中" not in game["difficulty"]


def test_daily_refresh_enrolls_all_five_without_relaxing_publication_guard():
    policy = json.loads((ROOT / "config" / "refresh_policy.json").read_text(encoding="utf-8"))
    for name in GUIDES:
        assert policy["games"][name]["enabled"] is True
        assert policy["games"][name]["adoptedBy"] == "CATALOG_2026_09_12"
    assert policy["publication"]["directRefreshNeverCreatesNewPublishedRows"] is True
    assert policy["publication"]["requireAutoPublishReady"] is True


def test_reference_rewards_are_display_only_until_verified_offer_exists():
    bootstrap = (ROOT / "games.js").read_text(encoding="utf-8")
    assert "loadOffersWithCatalogProvisionalFallback" in bootstrap
    assert 'dataSource: "catalog-provisional"' in bootstrap
    assert "verified: false" in bootstrap
    assert "gamesWithVerifiedOffer.has(gameName)" in bootstrap

    # The nightly strict gate may add verified offers for any of these games,
    # so check the rule rather than a fixed snapshot of which games have one.
    with (ROOT / "data" / "published_offers.csv").open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["game"] in GUIDES]
    verified = {row["game"] for row in rows if row["verified"] == "true"}
    assert "ATLAS: EARTH" in verified
    for row in rows:
        assert row["url"].startswith("https://"), row["offerKey"]

    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        catalog = {row["name"]: row for row in csv.DictReader(handle)}
    for name in set(GUIDES) - verified:
        # Without a verified offer the card may only show the reference reward.
        assert int(catalog[name]["provisionalReward"] or 0) > 0, name


# --- Game detail URLs in sitemap.xml -----------------------------------------------------
# This file is run by the "Validate five new guides" workflow, which also triggers on changes to
# sitemap.xml / games.csv / guides.html, so these checks run on the pull requests that can break them.
GAME_DETAIL_PREFIX = "https://poigamelab.com/game.html?game="
GAME_BLOCK_START = "<!-- POIGAME_GAME_DETAIL_URLS_START"
GAME_BLOCK_END = "<!-- POIGAME_GAME_DETAIL_URLS_END -->"


def _encode_uri_component(value):
    # Same unreserved set as JavaScript's encodeURIComponent (which builds the page canonical).
    return quote(value, safe="-_.!~*'()")


def _sitemap_game_locs(text):
    return [loc for loc in re.findall(r"<loc>([^<]+)</loc>", text) if "game.html" in loc]


def test_sitemap_game_detail_urls_are_the_urls_the_site_links_to_and_canonicalises_to():
    """Sitemap, internal links and the JS canonical must all name the same game URL.

    One-directional on purpose: a catalog game that is not (yet) listed is not an error here, but a
    listed URL must be a real catalog game written exactly like the internal links.
    """
    with (ROOT / "games.csv").open(encoding="utf-8-sig", newline="") as handle:
        catalog = {row["name"].strip() for row in csv.DictReader(handle) if row.get("name", "").strip()}
    locs = _sitemap_game_locs((ROOT / "sitemap.xml").read_text(encoding="utf-8"))
    assert locs, "game detail URLs are expected in the sitemap"
    assert len(locs) == len(set(locs))
    guides_html = (ROOT / "guides.html").read_text(encoding="utf-8")
    for loc in locs:
        assert loc.startswith(GAME_DETAIL_PREFIX), loc
        raw = loc[len(GAME_DETAIL_PREFIX):]
        assert "&" not in loc and "#" not in loc, loc
        name = unquote(raw)
        assert name in catalog, f"sitemap lists a game that is not in games.csv: {name}"
        assert raw == _encode_uri_component(name), f"not encodeURIComponent form: {loc}"
        assert f'href="game.html?game={raw}' in guides_html, f"guides.html does not link to {loc}"
    # The JS canonical is built with encodeURIComponent on the same prefix.
    game_html = (ROOT / "game.html").read_text(encoding="utf-8")
    assert "`" + GAME_DETAIL_PREFIX + "${encodeURIComponent(game.name)}`" in game_html


def test_sitemap_never_lists_the_bare_game_page():
    assert "https://poigamelab.com/game.html</loc>" not in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_guide_registration_scripts_keep_the_game_detail_block():
    """Publishing a researched game rewrites only its own marker block of sitemap.xml."""
    import include_generated_guides as include
    import register_generated_guides as registry

    original = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    assert GAME_BLOCK_START in original and GAME_BLOCK_END in original
    expected = _sitemap_game_locs(original)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        target = folder / "sitemap.xml"
        for _ in range(2):  # applying twice must neither duplicate nor drop anything
            shutil.copy2(ROOT / "sitemap.xml", target)
            include.patch_sitemap(folder, [{"guidePath": "new-game-guide.html"}])
            include.patch_sitemap(folder, [{"guidePath": "new-game-guide.html"}])
            text = target.read_text(encoding="utf-8")
            assert _sitemap_game_locs(text) == expected
            assert text.count("https://poigamelab.com/new-game-guide.html</loc>") == 1
            registry.patch_sitemap({"guides": {"x": {"guidePath": "other-guide.html"}}}, target)
            text = target.read_text(encoding="utf-8")
            assert _sitemap_game_locs(text) == expected
            assert text.count("https://poigamelab.com/other-guide.html</loc>") == 1
            registry.patch_sitemap({"guides": {}}, target)
            assert _sitemap_game_locs(target.read_text(encoding="utf-8")) == expected
