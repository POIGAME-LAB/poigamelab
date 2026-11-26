"""Candidates from the all-offers ranking and the minimum number of player-record searches (operator decision 2026-11-26)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_daily_selection as chk  # noqa: E402
import daily_guide_candidates as cand  # noqa: E402
import daily_guide_triage as triage  # noqa: E402

DATE = "2026-11-27"


def _write(tmp_path, decisions, verified=12):
    b = tmp_path / DATE
    b.mkdir()
    (b / "selection.json").write_text(json.dumps({"decisions": decisions}, ensure_ascii=False), encoding="utf-8")
    items = [{"game": f"g{i}", "verdict": "offer_verified", "bucket": "game_candidate"} for i in range(verified)]
    (b / "triage.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    return b


def _searched(n, decision="held"):
    return [{"game": f"ゲーム{i}", "decision": decision, "reason": "記録1人のみ",
             "playerSearch": {"queries": [f"ゲーム{i} ポイ活"], "recordsFound": 1, "independentPlayers": 1}} for i in range(n)]


def test_ten_searched_games_pass(tmp_path):
    assert chk.problems(_write(tmp_path, _searched(10))) == []


def test_too_few_searches_fail(tmp_path):
    assert chk.problems(_write(tmp_path, _searched(4))) == ["too_few_player_searches:4<10"]


def test_fewer_verified_offers_lower_the_minimum(tmp_path):
    assert chk.problems(_write(tmp_path, _searched(6), verified=6)) == []


def test_held_without_a_recorded_search_does_not_count(tmp_path):
    decisions = _searched(9) + [{"game": "未調査", "decision": "held", "reason": "時間切れ"}]
    errs = chk.problems(_write(tmp_path, decisions))
    assert "player_search_not_recorded:未調査" in errs and "too_few_player_searches:9<10" in errs


def test_five_completed_articles_need_no_more_searches(tmp_path):
    assert chk.problems(_write(tmp_path, _searched(5, decision="completed"))) == []


def test_batches_before_the_rule_are_not_checked():
    result = subprocess.run([sys.executable, "scripts/check_daily_selection.py", "--all"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def _fixture_root(tmp_path, ranking_games, ranking_date="2026-11-27T00:50:00+00:00", monitor_date="2026-11-27T00:50:00+00:00"):
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "research" / "daily-guides").mkdir(parents=True)
    (root / "data" / "new_game_content_queue.json").write_text(json.dumps({"checkedAt": monitor_date, "items": []}), encoding="utf-8")
    (root / "data" / "new_game_monitor.json").write_text(json.dumps({"checkedAt": monitor_date, "items": [
        {"titleHint": "ひとりだけの新作パズル（テスト用）", "source": "warau", "classification": "likely_game",
         "firstPartyCandidateUrl": "https://www.warau.jp/x/1", "rewardHint": None}]}, ensure_ascii=False), encoding="utf-8")
    (root / "data" / "all_offers_ranking.json").write_text(json.dumps({"checkedAt": ranking_date, "gameCount": len(ranking_games),
                                                                         "offerCount": 0, "games": ranking_games}, ensure_ascii=False), encoding="utf-8")
    (root / "config" / "point_value_rates.json").write_text((ROOT / "config" / "point_value_rates.json").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "research" / "daily-guides" / "aliases.json").write_text("{}", encoding="utf-8")
    return root


RANKING = [{"game": "みんなの農園（テスト用）", "siteCount": 4, "offers": [
    {"source": s, "url": f"https://example.com/{s}/1", "platformHint": "", "listingUpperBoundYen": 900, "verifiedRewardYen": None}
    for s in ("warau", "moppy", "amefuri", "mikoshi")]}]


def test_ranking_games_join_the_candidates_and_more_sites_come_first(tmp_path):
    out = cand.build(DATE, _fixture_root(tmp_path, RANKING))
    assert out["status"] == "ok" and out["allOffersRanking"]["used"] is True
    names = [g["game"] for g in out["candidates"]]
    assert names[0] == "みんなの農園（テスト用）"
    first = out["candidates"][0]
    assert first["siteCount"] == 4 and first["sources"] == ["amefuri", "mikoshi", "moppy", "warau"]
    assert triage.triage_offline(first)["scoreParts"]["multiSite"] == 4


def test_a_stale_ranking_adds_nothing(tmp_path):
    out = cand.build(DATE, _fixture_root(tmp_path, RANKING, ranking_date="2026-11-25T00:50:00+00:00"))
    assert out["status"] == "ok" and out["allOffersRanking"]["used"] is False
    assert [g["game"] for g in out["candidates"]] == ["ひとりだけの新作パズル"]  # display_name drops the bracket note
