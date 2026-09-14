import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
        elif name == "Merge Help: ホームデザインパズル":
            assert "実際のプレイヤー記録" in page
            assert "調査更新：2026-09-15" in page
        else:
            assert "未プレイ・公開情報を調査" in page
            assert "調査更新：2026-09-12" in page
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

    with (ROOT / "data" / "published_offers.csv").open(encoding="utf-8", newline="") as handle:
        published_games = {row["game"] for row in csv.DictReader(handle)}
    assert published_games.isdisjoint(GUIDES)
