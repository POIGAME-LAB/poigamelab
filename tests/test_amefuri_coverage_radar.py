import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_amefuri_first_party_radar_is_partial_and_candidate_only():
    cfg = json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))
    source = next(item for item in cfg["sources"] if item["id"] == "amefuri")
    assert source["direct_listing_urls"] == ["https://www.amefri.net/item_list?slug=app_game"]
    assert source["coverage_first_party_listing_enabled"] is True
    assert source["coverage_scope"] == "partial_first_page_game_listing"
    assert source["scheduled_fetch_enabled"] is False
    assert "/detail/id/" in source["direct_detail_url_hints"]

    refresh = (ROOT / "scripts/direct_offer_refresh.py").read_text(encoding="utf-8")
    assert 'r"/detail/id/(\\d+)"' in refresh
