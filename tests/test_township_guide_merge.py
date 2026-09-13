from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_township_catalog_points_only_to_unified_lv70_guide():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    township_block = catalog.split('"Township": {', 1)[1].split('  "きのこ伝説": {', 1)[0]
    assert 'href: "township-lv70.html"' in township_block
    assert 'township-lv60.html' not in township_block
    assert 'label: "攻略を見る →"' in township_block


def test_unified_article_contains_lv60_and_lv70_content():
    page = (ROOT / "township-lv70.html").read_text(encoding="utf-8")
    assert "Township Lv60〜Lv70 ポイ活攻略" in page
    assert 'id="lv60"' in page
    assert 'id="heli"' in page
    assert 'id="barn"' in page
    assert 'id="tracking"' in page
    assert "約49日" in page
    assert "1,600円" in page
    assert "8月31日" in page
    assert "9月11日" in page
    assert "helicopter-order.jpg" in page
    assert "lv70-achieved.jpg" in page


def test_legacy_lv60_url_redirects_to_unified_article():
    legacy = (ROOT / "township-lv60.html").read_text(encoding="utf-8")
    assert "township-lv70.html#lv60" in legacy
    assert 'rel="canonical" href="https://poigamelab.com/township-lv70.html"' in legacy
    assert 'content="noindex,follow"' in legacy


def test_sitemap_only_indexes_unified_township_article():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://poigamelab.com/township-lv70.html" in sitemap
    assert "https://poigamelab.com/township-lv60.html" not in sitemap
