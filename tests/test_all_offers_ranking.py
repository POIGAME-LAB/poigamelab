"""All new-game offers on today's listings, ranked by listing amount (operator request 2026-11-24)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import daily_scan_review as daily  # noqa: E402
import write_all_offers_ranking as writer  # noqa: E402
from test_daily_scan_review import candidates, inspect, scan, sources  # noqa: E402


def _with_amount(items, text, offer_id=None):
    out = [{**i, "listingRewardText": text} for i in items]
    if offer_id:
        out = [{**i, "firstPartyCandidateUrl": i["firstPartyCandidateUrl"].replace("id=1", f"id={offer_id}")} for i in out]
    return out


def test_single_site_games_are_listed_with_their_listing_amount_without_extra_requests(monkeypatch):
    calls = []

    def counting_inspect(url, source, aliases, fetcher):
        calls.append(url)
        return inspect(url, source, aliases, fetcher)

    items = (_with_amount(candidates("Single Site Game", sites=("a",)), "3,000円", 7)
             + _with_amount(candidates("Two Site Game", sites=("a", "b")), "1,200円"))
    result = scan(items, monkeypatch, inspector=counting_inspect)
    ranking = result["allOffers"]
    assert ranking["gameCount"] == 2 and ranking["offerCount"] == 3
    assert [g["game"] for g in ranking["games"]] == ["Single Site Game", "Two Site Game"]  # by listing amount
    single = ranking["games"][0]
    assert single["siteCount"] == 1 and single["bestListingYen"] == 3000 and single["bestVerifiedYen"] is None
    # only the two-site game spent detail requests (unchanged behaviour); the summary added none
    assert len(calls) == 2
    two = ranking["games"][1]
    assert two["bestVerifiedYen"] == 2000 and {o["source"] for o in two["offers"]} == {"a", "b"}


def test_unknown_amounts_sort_last_and_existing_games_stay_out(monkeypatch):
    items = (candidates("No Amount Game", sites=("a",))
             + _with_amount(candidates("天地英雄伝", sites=("a",)), "9,999円", 8)
             + _with_amount(candidates("Cheap Game", sites=("b",)), "100円", 9))
    ranking = scan(items, monkeypatch, existing_games={"天地英雄伝"})["allOffers"]
    assert [g["game"] for g in ranking["games"]] == ["Cheap Game", "No Amount Game"]
    assert ranking["games"][1]["bestListingYen"] is None


def test_writer_builds_candidate_only_file_and_never_blocks_the_refresh(tmp_path, monkeypatch):
    review = {"checkedAt": "2026-11-24T16:30:00+00:00", "rankingComplete": False,
              "incompleteDiscoverySources": ["nifty_point"],
              "allOffers": {"gameCount": 1, "offerCount": 1, "offersBySource": {"a": 1},
                            "games": [{"game": "X", "siteCount": 1, "bestListingYen": 10, "bestVerifiedYen": None,
                                       "offers": []}]}}
    out = writer.build(review)
    assert out["candidateOnly"] is True and out["publicationAuthorized"] is False
    assert out["rankingCompleteForTopFive"] is False and out["incompleteDiscoverySources"] == ["nifty_point"]
    monkeypatch.setattr(writer, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    assert writer.main() == 0  # missing review: warns, does not fail
    (tmp_path / "data/daily_scan_review.json").write_text(json.dumps(review), encoding="utf-8")
    assert writer.main() == 0
    assert json.loads((tmp_path / "data/all_offers_ranking.json").read_text(encoding="utf-8"))["gameCount"] == 1


def test_workflow_writes_and_commits_the_ranking_but_not_the_private_review():
    text = (ROOT / ".github/workflows/refresh-verified-offers.yml").read_text(encoding="utf-8")
    assert "python scripts/write_all_offers_ranking.py" in text
    assert "git add data/all_offers_ranking.json" in text
    assert "git add data/daily_scan_review.json" not in text
