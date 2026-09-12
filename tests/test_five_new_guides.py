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


def test_new_guides_exist_and_disclose_research_status():
    for name, filename in GUIDES.items():
        page = (ROOT / filename).read_text(encoding="utf-8")
        assert name.split(":")[0] in page
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


def test_all_five_are_formal_catalog_games_with_temporary_image_and_reference_reward():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}

    for name in GUIDES:
        assert name in rows
        row = rows[name]
        assert row["image"] == "poigamelab_hero.png"
        assert int(row["provisionalReward"]) > 0
        assert row["provisionalSource"].strip()
        assert row["addedDate"] == "2026-09-12"


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
