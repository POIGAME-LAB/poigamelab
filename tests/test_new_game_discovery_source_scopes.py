import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_new_game_discovery_sources_keep_full_vs_partial_scope():
    cfg = json.loads((ROOT / "config" / "point_sources.json").read_text(encoding="utf-8"))

    by_id = {item["id"]: item for item in cfg["sources"]}
    ec = by_id["ec_navi"]
    powl = by_id["powl"]
    point_town = by_id["point_town"]

    assert ec["new_game_discovery_enabled"] is True
    assert ec["full_catalog_discovery_enabled"] is True
    assert ec["new_game_discovery_scope"] == "full_current_category_listing"

    assert powl["new_game_discovery_enabled"] is True
    assert powl["full_catalog_discovery_enabled"] is False
    assert powl["new_game_discovery_scope"] == "partial_ranked_app_listing"

    assert point_town["new_game_discovery_enabled"] is True
    assert point_town["full_catalog_discovery_enabled"] is False
    assert point_town["new_game_discovery_scope"] == "partial_web_app_install_listing"


def test_partial_sources_are_positive_detection_only():
    refresh = (ROOT / "scripts" / "direct_offer_refresh.py").read_text(encoding="utf-8")

    assert 'and x.get("full_catalog_discovery_enabled") is True' not in refresh.split(
        "new_game_discovery_sources = [", 1
    )[1].split("]", 1)[0]
    assert '"discoveryScope": str(source.get("new_game_discovery_scope")' in refresh
    assert '"fullCatalogObserved": source.get("full_catalog_discovery_enabled") is True' in refresh
    assert '"autoCreateAuthorized": False' in refresh
    assert '"publicationAuthorized": False' in refresh
