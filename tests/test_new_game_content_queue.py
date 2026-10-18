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


def test_catalogued_game_is_skipped_and_next_new_candidate_is_promoted():
    out = queue.build(report(), existing_games={"Game 6"})
    assert out["count"] == 5
    assert [x["game"] for x in out["items"]] == [f"Game {i}" for i in (5, 4, 3, 2, 1)]
    assert [x["rank"] for x in out["items"]] == [1, 2, 3, 4, 5]


def test_write_reads_games_csv_and_excludes_existing_game():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inp = td / "review.json"
        outp = td / "queue.json"
        catalog = td / "games.csv"
        inp.write_text(json.dumps(report()), encoding="utf-8")
        catalog.write_text("name,image\nGame 6,old.png\n", encoding="utf-8")
        saved = queue.write(inp, outp, catalog)
        assert saved["count"] == 5
        assert [x["game"] for x in saved["items"]] == [f"Game {i}" for i in (5, 4, 3, 2, 1)]


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


def test_single_listing_source_is_held_not_promoted():
    bad = report()
    bad["results"][5] = row("Game 6", 6000, sources=("warau",))
    out = queue.build(bad)
    assert "Game 6" not in [x["game"] for x in out["items"]]
    assert out["heldCandidates"] == [{"game": "Game 6", "reason": "ranked_game_listing_sources_below_two"}]
    # the next ranked game fills the freed slot
    assert out["count"] == 5
    assert out["items"][-1]["game"] == "Game 1"


def test_workflow_writes_archives_and_commits_queue_once():
    workflow = (ROOT / ".github/workflows/refresh-verified-offers.yml").read_text(encoding="utf-8")
    assert "python scripts/write_new_game_content_queue.py" in workflow
    assert "data/new_game_content_queue.json" in workflow
    assert workflow.count("git add data/new_game_content_queue.json") == 1


def test_write_treats_reviewed_target_aliases_as_listed_games():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inp, outp, catalog, targets = (td / n for n in ("review.json", "queue.json", "games.csv", "targets.json"))
        inp.write_text(json.dumps(report()), encoding="utf-8")
        catalog.write_text("name,image\nListed Game,\n", encoding="utf-8")
        targets.write_text(json.dumps({"games": [
            {"game": "Listed Game", "aliases": ["Listed Game", "Game 6"], "known_urls_by_source": {}}]}),
            encoding="utf-8")
        saved = queue.write(inp, outp, catalog, targets)
        assert [x["game"] for x in saved["items"]] == [f"Game {i}" for i in (5, 4, 3, 2, 1)]


def test_real_targets_mark_the_subtitled_wild_survival_title_as_listed():
    assert "Wild Survival - 野蛮な生存者：最後の戦い" in queue.load_target_aliases()


# --- 2026-10 regression: ranked_game_reward_invalid aborted the daily refresh ---

@pytest.mark.parametrize("bad_reward", [1234.5, 0, -5, True, "1500", None])
def test_invalid_reward_holds_only_that_candidate(bad_reward):
    # Powl can legitimately expose a fractional-yen reward (e.g. 1234.5). The
    # downstream research stage truncates with int(), so it must never be queued.
    data = report()
    data["results"][5]["maxObservedRewardYen"] = bad_reward
    out = queue.build(data)
    games = [x["game"] for x in out["items"]]
    assert "Game 6" not in games
    assert {"game": "Game 6", "reason": "ranked_game_reward_invalid"} in out["heldCandidates"]
    assert out["count"] == 5 and games == [f"Game {i}" for i in (5, 4, 3, 2, 1)]
    assert all(type(x["maxObservedRewardYen"]) is int and x["maxObservedRewardYen"] > 0 for x in out["items"])
    assert all(x["publicationAuthorized"] is False for x in out["items"])
    assert out["publicationAuthorized"] is False and out["candidateOnly"] is True


def test_every_candidate_invalid_yields_empty_authorizationless_queue():
    data = report()
    for r in data["results"]:
        r["maxObservedRewardYen"] = 99.5
    out = queue.build(data)
    assert out["count"] == 0 and out["items"] == []
    assert len(out["heldCandidates"]) >= 5
    assert out["publicationAuthorized"] is False


def test_malformed_candidate_fields_are_held_not_raised():
    data = report()
    data["results"][5]["confirmedSourceCount"] = [1]
    data["results"][4]["details"] = [{"source": "warau", "finalUrl": "http://insecure.example/x", "rewardYen": 5000}]
    out = queue.build(data)
    held = {h["game"]: h["reason"] for h in out["heldCandidates"]}
    assert held["Game 6"] == "ranked_game_fields_invalid"
    assert held["Game 5"] == "ranked_game_listing_sources_below_two"
    assert out["count"] == 4


def _write_report(tmp_path, data):
    path = tmp_path / "daily_scan_review.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _catalog(tmp_path):
    path = tmp_path / "games.csv"
    path.write_text("name\nExisting Game\n", encoding="utf-8")
    return path


def test_write_persists_held_candidates_and_remaining_queue(tmp_path):
    data = report()
    data["results"][5]["maxObservedRewardYen"] = 1234.5
    out = queue.write(_write_report(tmp_path, data), tmp_path / "out.json", _catalog(tmp_path), tmp_path / "missing_targets.json")
    saved = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert saved == out
    assert saved["rankingComplete"] is True and saved["count"] == 5
    assert saved["heldCandidates"][0]["reason"] == "ranked_game_reward_invalid"


def test_main_warns_but_exits_zero_when_candidates_are_held(tmp_path, monkeypatch, capsys):
    data = report()
    data["results"][5]["maxObservedRewardYen"] = 1234.5
    paths = (_write_report(tmp_path, data), tmp_path / "out.json", _catalog(tmp_path), tmp_path / "none.json")
    real_write = queue.write
    monkeypatch.setattr(queue, "write", lambda: real_write(*paths))
    assert queue.main() == 0
    printed = capsys.readouterr().out
    assert "::warning::new-game candidate held: Game 6 (ranked_game_reward_invalid)" in printed


@pytest.mark.parametrize("payload", [
    "{not json",
    json.dumps({"phase": "OTHER"}),
    json.dumps({"phase": "DAILY_SAME_SCAN_REVIEW_V1", "topFiveReviewCandidates": "x", "results": []}),
    json.dumps([]),
])
def test_unusable_report_becomes_empty_handoff_not_a_crash(tmp_path, payload):
    inp = tmp_path / "daily_scan_review.json"
    inp.write_text(payload, encoding="utf-8")
    out = queue.write(inp, tmp_path / "out.json", _catalog(tmp_path), tmp_path / "none.json")
    assert out["count"] == 0 and out["items"] == []
    assert out["rankingComplete"] is False
    assert out["holdReason"].startswith("queue_build_error") or out["holdReason"].startswith("queue_input_unavailable")
    assert out["publicationAuthorized"] is False


def test_missing_report_or_catalog_becomes_empty_handoff(tmp_path):
    out = queue.write(tmp_path / "nope.json", tmp_path / "out1.json", _catalog(tmp_path), tmp_path / "none.json")
    assert out["count"] == 0 and out["holdReason"].startswith("queue_input_unavailable")
    out = queue.write(_write_report(tmp_path, report()), tmp_path / "out2.json", tmp_path / "nogames.csv", tmp_path / "none.json")
    assert out["count"] == 0 and out["holdReason"].startswith("queue_input_unavailable")
    assert not list(tmp_path.glob("*.tmp"))


def test_queue_stage_never_touches_published_offer_files(tmp_path):
    # The queue writer only writes its own output path.
    before = {p.name for p in ROOT.glob("data/*.csv")}
    queue.write(_write_report(tmp_path, report()), tmp_path / "out.json", _catalog(tmp_path), tmp_path / "none.json")
    assert {p.name for p in ROOT.glob("data/*.csv")} == before
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".csv") and p.name != "games.csv"] == []


def test_root_cause_fractional_yen_reaches_ranking_but_not_the_queue():
    # 2026-10-16/17: "Heroes Survival Battle" ranked 5th with 24945.6 yen
    # (Kurashiru Reward, 100coin=1JPY). The scan accepts fractional yen for
    # ranking; the queue contract is integer yen, so only the queue holds it.
    import daily_scan_review as scan

    evidence = {
        "state": "parsed", "parserVersion": "kurashiru-reward-detail-review-v2",
        "verifiedCurrentRewardCoins": 2494560, "verifiedCurrentRewardYen": 24945.6,
        "rewardUnit": "Kurashiru-coin", "sourcePointRate": "100coin=1JPY",
    }
    value = scan.explicit_yen(evidence)
    assert value == 24945.6 and type(value) is float

    data = report()
    data["results"][5]["maxObservedRewardYen"] = value
    data["topFiveReviewCandidates"] = [f"Game {i}" for i in (5, 4, 3, 2, 6)]
    out = queue.build(data)
    assert [h["game"] for h in out["heldCandidates"]] == ["Game 6"]
    assert [x["game"] for x in out["items"]] == [f"Game {i}" for i in (5, 4, 3, 2, 1)]
