import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import write_new_game_content_queue as queue


def row(game, reward, sources=("warau", "moppy")):
    return {
        "game": game,
        "candidateEligible": True,
        "confirmedSourceCount": len(sources),
        "listingSourceCount": len(sources),
        "verifiedRewardSourceCount": 1 if sources else 0,
        "maxObservedRewardYen": reward,
        "publicationAuthorized": False,
        "researchQueries": {
            "web": f'"{game}" web', "x": f'"{game}" x', "youtube": f'"{game}" youtube',
            "instagram": f'"{game}" instagram', "point_site_reviews": f'"{game}" reviews',
        },
        "details": [
            {
                "source": sid,
                "detailConfirmed": True,
                "finalUrl": f"https://{sid}.example/detail/{i}",
                "rewardYen": reward if i == 1 else None,
            }
            for i, sid in enumerate(sources, 1)
        ],
    }


def report():
    rows = [row(f"Game {i}", i * 1000) for i in range(1, 7)]
    return {
        "phase": "DAILY_SAME_SCAN_REVIEW_V1",
        "checkedAt": "2026-09-15T16:17:00+00:00",
        "topFiveReviewCandidates": [f"Game {i}" for i in (6, 5, 4, 3, 2)],
        "results": rows,
    }


def test_build_keeps_rank_order_and_never_authorizes_publication():
    out = queue.build(report())
    assert out["count"] == 5
    assert [x["game"] for x in out["items"]] == [f"Game {i}" for i in (6, 5, 4, 3, 2)]
    assert [x["rank"] for x in out["items"]] == [1, 2, 3, 4, 5]
    assert all(x["publicationAuthorized"] is False for x in out["items"])
    assert all(set(x["requiredResearchChannels"]) == {"web", "x", "youtube", "instagram", "pointSites"} for x in out["items"])


def test_write_is_atomic_compact_handoff():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); inp = td / "review.json"; outp = td / "queue.json"
        inp.write_text(json.dumps(report()), encoding="utf-8")
        result = queue.write(inp, outp)
        saved = json.loads(outp.read_text(encoding="utf-8"))
        assert saved == result and saved["phase"] == "NEW_GAME_CONTENT_QUEUE_V1"


def test_one_verified_reward_with_two_listing_sources_is_valid_research_handoff():
    value = report()
    candidate = row("Game 6", 6000)
    candidate["confirmedSourceCount"] = 1
    candidate["details"][1]["detailConfirmed"] = False
    value["results"][5] = candidate
    out = queue.build(value)
    top = out["items"][0]
    assert top["game"] == "Game 6"
    assert top["listingSourceCount"] == 2
    assert top["verifiedRewardSourceCount"] == 1
    assert len({x["source"] for x in top["pointSiteEvidence"]}) == 2
    assert top["publicationAuthorized"] is False


def test_single_listing_source_still_fails_closed():
    bad = report()
    bad["results"][5] = row("Game 6", 6000, sources=("warau",))
    with pytest.raises(ValueError, match="listing_sources_below_two"):
        queue.build(bad)


def test_workflow_writes_archives_and_commits_queue_once():
    workflow = (ROOT / ".github/workflows/refresh-verified-offers.yml").read_text(encoding="utf-8")
    assert "python scripts/write_new_game_content_queue.py" in workflow
    assert "data/new_game_content_queue.json" in workflow
    assert workflow.count("git add data/new_game_content_queue.json") == 1
