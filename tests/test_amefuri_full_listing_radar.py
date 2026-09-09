import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_amefuri_radar_covers_all_reviewed_game_listing_pages():
    cfg = json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))
    source = next(item for item in cfg["sources"] if item["id"] == "amefuri")
    urls = source["direct_listing_urls"]
    assert len(urls) == 26
    assert urls[0] == "https://www.amefri.net/item_list?slug=app_game"
    assert urls[-1] == "https://www.amefri.net/item_list?page=26&slug=app_game"
    assert source["direct_listing_limit"] == 26
    assert source["coverage_scope"] == "full_paginated_game_listing"
    assert source["scheduled_fetch_enabled"] is False

    refresh = (ROOT / "scripts/direct_offer_refresh.py").read_text(encoding="utf-8")
    assert "fetch_cache = {}" in refresh
    assert "def fetch_once(url, source):" in refresh
