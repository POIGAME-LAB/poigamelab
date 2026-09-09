import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offerwall_capability_model_is_explicit():
    cfg = json.loads((ROOT / "config" / "offerwall_providers.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in cfg["providers"]}

    assert cfg["capabilityModel"]["version"] == 1

    mychips = by_id["mychips"]
    assert "sdk.mychips.io" in mychips["presenceDomains"]
    assert mychips["collectionCapability"] == "presence_only_without_publisher_context"
    assert mychips["directCatalogEligible"] is False

    skyflag = by_id["skyflag"]
    assert skyflag["collectionCapability"] == "presence_only_without_publisher_context"
    assert skyflag["directCatalogEligible"] is False

    appdriver = by_id["appdriver"]
    assert appdriver["collectionCapability"] == "publisher_api_available_credentials_required"
    assert appdriver["publisherApiAvailable"] is True
    assert appdriver["directCatalogEligible"] is False


def test_no_offerwall_is_accidentally_authorized_for_direct_catalog():
    cfg = json.loads((ROOT / "config" / "offerwall_providers.json").read_text(encoding="utf-8"))
    assert all(item.get("directCatalogEligible") is False for item in cfg["providers"])
