"""MIKOSHI: existing-game lane and publication contract (operator decision 2026-11-24, real pages)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct  # noqa: E402
import structured_publication as pub  # noqa: E402

FIX = ROOT / "tests/fixtures/daily_pages/mikoshi"
SOURCES = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
TARGETS = json.loads((ROOT / "config/game_targets.json").read_text(encoding="utf-8"))["games"]
POLICY = json.loads((ROOT / "config/refresh_policy.json").read_text(encoding="utf-8"))["structuredPublication"]
FEED = "https://web.mikoshi.jp/v2/skyflag/ads?os=1&limit=1000"
NOW = "2026-11-24T16:30:00+00:00"


def _aliases(game):
    target = next(t for t in TARGETS if t["game"] == game)
    return [game] + target.get("aliases", [])


def _item(offer_id, game):
    url = f"https://web.mikoshi.jp/v2/skyflag/ads/{offer_id}"
    raw = (FIX / f"{offer_id}.json").read_text(encoding="utf-8")
    detail = direct.inspect_detail(url, SOURCES["mikoshi"], _aliases(game), fetcher=lambda u, s: (raw, url))
    return {"origin": "current_first_party_detail", "game": game, "source": "mikoshi", "requestedUrl": url,
            "url": detail["url"], "sourceEvidence": detail["sourceEvidence"], "checkedAt": NOW}


def _run(rows, items):
    return pub.prepare_verified(rows, items, SOURCES, NOW, POLICY, {t["game"] for t in TARGETS}, TARGETS, True)


def test_mikoshi_joins_the_existing_game_lane_and_publication():
    assert SOURCES["mikoshi"]["existing_game_listing_lane"] is True
    assert "mikoshi" in POLICY["sources"] and "mikoshi" in pub.REWARD_ONLY_CONTRACTS


def test_feed_finds_catalog_games_by_their_detail_url():
    raw = (FIX / "feed_os1.json").read_text(encoding="utf-8")
    found = direct.discover_first_party_listing_candidates(raw, FEED, SOURCES["mikoshi"], _aliases("キングショット"))
    assert [c["firstPartyCandidateUrl"] for c in found] == ["https://web.mikoshi.jp/v2/skyflag/ads/36150"]
    kinoko = direct.discover_first_party_listing_candidates(raw, FEED, SOURCES["mikoshi"], _aliases("きのこ伝説"))
    assert "https://web.mikoshi.jp/v2/skyflag/ads/35331" in [c["firstPartyCandidateUrl"] for c in kinoko]
    assert direct.discover_first_party_listing_candidates(raw, FEED, SOURCES["mikoshi"], ["存在しないゲーム名"]) == []


@pytest.mark.parametrize("offer_id, game, yen, kind, steps", [
    ("36150", "キングショット", "9110", "StepUp", 9),
    ("35331", "きのこ伝説", "12654", "StepUp", 8),
    ("22431", "東京ディバンカー", "322", "Single", 1),
])
def test_real_details_publish_with_every_step_in_the_condition(offer_id, game, yen, kind, steps):
    out, report = _run([], [_item(offer_id, game)])
    assert report["decisions"][0].get("holdReason") is None, report["decisions"]
    row = out[0]
    assert (row["site"], row["reward"], row["type"]) == ("mikoshi", yen, kind)
    if kind == "StepUp":
        assert row["condition"].count("MIKOSHIポイント】") == steps and "STEP1：" in row["condition"]
    assert row["platform"] in {"iOS", "Android"}


def test_step_sum_and_fingerprint_are_enforced():
    item = _item("36150", "キングショット")
    item["sourceEvidence"]["steps"][0]["rewardPoints"] += 1
    out, report = _run([], [item])
    assert out == [] and "holdReason" in report["decisions"][0]


def test_item_level_candidate_envelope_still_vetoes():
    item = _item("36150", "キングショット")
    item["candidateOnly"] = True
    out, report = _run([], [item])
    assert out == [] and report["decisions"][0]["holdReason"] == "candidate_only_input"


def test_other_parsers_marked_candidate_only_still_hold():
    contract = copy.deepcopy(pub.REWARD_ONLY_CONTRACTS["powl"])
    assert contract.get("parserCandidateOnlyIsDefault") is not True
