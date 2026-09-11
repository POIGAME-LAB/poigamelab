import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


def test_moppy_uses_reviewed_first_party_ajax_pagination_and_keeps_guardrails():
    payload = json.loads((ROOT / "config" / "point_sources.json").read_text(encoding="utf-8"))
    source = next(item for item in payload["sources"] if item["id"] == "moppy")

    assert source["mobile"] is False
    assert source["new_game_discovery_enabled"] is True
    assert source["full_catalog_discovery_enabled"] is False
    assert source["new_game_discovery_min_detail_identities_first_page"] == 1
    assert source["new_game_discovery_scope"] == "paginated_first_party_ajax_app_listing"

    template = source["new_game_discovery_page_url_template"]
    assert template.count("{page}") == 1
    parsed = urlparse(template.replace("{page}", "7"))
    assert parsed.scheme == "https"
    assert parsed.hostname == "pc.moppy.jp"
    assert parsed.path == "/ajax/category/get_list.php"
    query = parse_qs(parsed.query, keep_blank_values=True)
    assert query["parent_category"] == ["4"]
    assert query["child_category"] == ["52"]
    assert query["current_page"] == ["7"]
    assert query["af_sorter"] == ["1"]
    assert "objective_category" in query
    assert "exclude_purchased" in query
    assert "publication remains gated" in source["discoveryNote"].lower()
