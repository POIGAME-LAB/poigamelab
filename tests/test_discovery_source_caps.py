import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(source_id):
    payload = json.loads((ROOT / "config" / "point_sources.json").read_text(encoding="utf-8"))
    return next(item for item in payload["sources"] if item.get("id") == source_id)


def test_powl_discovery_cap_does_not_truncate_at_100():
    powl = _source("powl")
    assert powl["new_game_discovery_candidate_limit"] == 500


def test_powl_remains_partial_catalog_after_cap_increase():
    powl = _source("powl")
    assert powl.get("full_catalog_discovery_enabled") is False
    assert powl["new_game_discovery_scope"] == "partial_ranked_app_listing"
