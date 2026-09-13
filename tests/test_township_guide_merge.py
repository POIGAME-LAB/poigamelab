from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_township_catalog_points_to_lv70_guide():
    catalog = (ROOT / "site-guides.js").read_text(encoding="utf-8")
    township_block = catalog.split('"Township": {', 1)[1].split('  "きのこ伝説": {', 1)[0]
    assert 'href: "township-lv70.html"' in township_block
    assert 'label: "攻略を見る →"' in township_block


def test_lv70_article_is_standalone_again():
    page = (ROOT / "township-lv70.html").read_text(encoding="utf-8")
    assert "Township Lv70を実際に約49日でクリア" in page
    assert "Township Lv60〜Lv70 ポイ活攻略" not in page
    assert 'id="lv60"' not in page
    assert "Lv60までの基礎攻略" not in page
    assert "約49日" in page
    assert "1,600円" in page
    assert "9月11日" in page
    assert "helicopter-order.jpg" in page


def test_township_progress_cta_is_kept_in_shared_header():
    header = (ROOT / "site-header.js").read_text(encoding="utf-8")
    assert 'filename !== "township-lv70.html"' in header
    assert 'progress.html?game=Township' in header
    assert 'みんなの進捗を見る →' in header
