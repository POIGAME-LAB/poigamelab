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
        assert f'https://poigamelab.com/{filename}' in page
        assert "site-header.js" in page
        assert "site-footer.js" in page


def test_site_guide_registry_links_every_new_page():
    registry = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    for name, filename in GUIDES.items():
        assert f'"{name}"' in registry
        assert f'href: "{filename}"' in registry


def test_guide_hub_renders_researched_guides_outside_catalog():
    hub = (ROOT / "guides.html").read_text(encoding="utf-8")
    assert "Object.entries(window.POIGAME_GUIDES || {})" in hub
    assert "rendered.has(name)" in hub
    assert "未プレイ・公開情報を調査した新着ガイド" in hub


def test_sitemap_contains_every_new_guide():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    for filename in GUIDES.values():
        assert f"https://poigamelab.com/{filename}" in sitemap
