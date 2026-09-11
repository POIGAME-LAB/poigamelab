import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hapitas_discovery_uses_desktop_user_agent_and_stays_candidate_only():
    payload = json.loads((ROOT / "config" / "point_sources.json").read_text(encoding="utf-8"))
    source = next(item for item in payload["sources"] if item["id"] == "hapitas")

    assert source["mobile"] is False
    assert source["new_game_discovery_enabled"] is True
    assert source["full_catalog_discovery_enabled"] is True
    assert source["coverage_first_party_listing_enabled"] is True
    assert source["discovery_only"] is True
    assert source["scheduled_fetch_enabled"] is False
    assert source["coverage_detail_review_mode"] == "candidate_only"
    assert "publication remains disabled" in source["discoveryNote"].lower()
