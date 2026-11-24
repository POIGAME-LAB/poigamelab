"""Amefuri listing cards (real page, 2026-11-24): the title sits beside an empty overlay link."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct  # noqa: E402

SOURCES = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
RAW = (ROOT / "tests/fixtures/daily_pages/amefuri_game_listing_page2.html").read_text(encoding="utf-8")
URL = "https://www.amefri.net/item_list?page=2&slug=app_game"


def test_catalog_game_on_amefuri_listing_is_found_through_its_card():
    found = direct.discover_first_party_listing_candidates(RAW, URL, SOURCES["amefuri"], ["きのこ伝説", "キノコ伝説"], limit=8)
    assert [c["firstPartyCandidateUrl"] for c in found] == ["https://www.amefri.net/detail/id/141876"]
    assert all(c["source"] == "amefuri" for c in found)


def test_cards_do_not_leak_to_neighbours_and_unknown_games_match_nothing():
    # 杖と剣の伝説 and キノコ伝説 are neighbouring cards on this page: each binds only its own link
    tsue = direct.discover_first_party_listing_candidates(RAW, URL, SOURCES["amefuri"], ["杖と剣の伝説"], limit=8)
    assert [c["firstPartyCandidateUrl"] for c in tsue] == ["https://www.amefri.net/detail/id/142276"]
    assert direct.discover_first_party_listing_candidates(RAW, URL, SOURCES["amefuri"], ["存在しないゲーム名"], limit=8) == []


def test_without_the_reviewed_card_token_the_old_behaviour_found_nothing():
    source = {k: v for k, v in SOURCES["amefuri"].items() if k != "listing_card_class_tokens"}
    assert direct.discover_first_party_listing_candidates(RAW, URL, source, ["キノコ伝説"], limit=8) == []
