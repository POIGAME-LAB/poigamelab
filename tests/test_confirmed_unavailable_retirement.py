"""Published rows leave only after the source said "ended" on 3 nightly runs."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_scan_review as daily  # noqa: E402
import structured_publication as pub  # noqa: E402
import validate_daily_publication as validator  # noqa: E402
from tests.test_direct_offer_refresh_v1 import warau_markup  # noqa: E402,F401
from tests.test_structured_publication import sample, NOW  # noqa: E402
from tests.test_verified_existing_publication import envelope, run  # noqa: E402


def ended(item, runs=None, checked_at=NOW):
    out = envelope(dict(item, checkedAt=checked_at, sourceEvidence={
        "state": "unavailable", "reason": "source_offer_unavailable", "offerId": "101"}))
    if runs is not None:
        out["consecutiveUnavailableRuns"] = runs
    return out


@pytest.mark.parametrize("runs", [None, 1, 2])
def test_row_is_held_until_three_ended_runs(warau_markup, runs):
    row, item = sample(warau_markup)
    out, report = run([row], [ended(item, runs)])
    assert out == [row]
    assert report["decisions"][0]["holdReason"] == "unavailable_not_yet_confirmed"
    assert report["retiredRows"] == 0


def test_third_ended_run_retires_only_that_row(warau_markup):
    row, item = sample(warau_markup)
    other = dict(row, offerKey="other", url=row["url"].replace("101", "202"))
    out, report = run([row, other], [ended(item, 3)])
    assert out == [other]
    decision = report["decisions"][0]
    assert decision["retired"] is True and decision["offerKey"] == row["offerKey"]
    assert decision["publicationMode"] == "confirmed_unavailable_retirement"
    assert decision["consecutiveUnavailableRuns"] == 3
    assert report["retiredRows"] == 1 and report["updatedRows"] == 0


@pytest.mark.parametrize("change", [
    {"checkedAt": "2026-09-14T16:17:00+00:00"},          # reading from another run
    {"game": "別のゲーム"},                              # another game's reading
    {"sourceEvidence": {"state": "unavailable", "reason": "source_offer_unavailable",
                        "offerId": "999"}},              # a different offer id
])
def test_unclear_ended_readings_never_retire(warau_markup, change):
    row, item = sample(warau_markup)
    snapshot = dict(ended(item, 5), **change)
    out, report = run([row], [snapshot])
    assert out == [row]
    assert report["decisions"][0].get("holdReason")


def test_mixed_live_and_ended_readings_hold_the_row(warau_markup):
    row, item = sample(warau_markup)
    out, report = run([row], [ended(item, 5), envelope(item)])
    assert out == [row]
    assert report["decisions"][0]["holdReason"] == "conflicting_current_evidence"


def test_other_sources_are_never_retired_by_this_path(warau_markup):
    row, item = sample(warau_markup)
    moppy_row = dict(row, site="moppy", url="https://pc.moppy.jp/ad/detail.php?site_id=5")
    snapshot = ended(dict(item, source="moppy", url=moppy_row["url"]), 5)
    sources = {"moppy": {"id": "moppy", "search_domains": ["pc.moppy.jp"]}}
    out, report = pub.prepare_verified([moppy_row], [snapshot], sources, NOW,
                                       {"enabled": True, "verifiedExistingGameGate": True,
                                        "sources": ["moppy"]}, {"テストゲーム"}, [], True)
    assert out == [moppy_row]
    assert report["decisions"][0]["holdReason"] == "source_offer_unavailable"


def reading(state, checked_at, point_id="101"):
    evidence = {"state": state}
    if state == "unavailable":
        evidence.update(reason="source_offer_unavailable", offerId=point_id)
    return {"source": "warau", "game": "テストゲーム", "checkedAt": checked_at,
            "url": f"https://www.warau.jp/contents/point/pointEntrance.php?point_id={point_id}",
            "sourceEvidence": evidence}


def test_counts_need_separate_runs_and_reset_on_a_live_page(tmp_path):
    path = tmp_path / "offer_unavailable_runs.json"
    for n, checked_at in enumerate(("t1", "t2"), 1):
        out = daily.track_unavailable_runs([reading("unavailable", checked_at)], checked_at, path)
        assert out[0]["consecutiveUnavailableRuns"] == n
    # The same run read twice is still one run.
    out = daily.track_unavailable_runs([reading("unavailable", "t2")], "t2", path)
    assert out[0]["consecutiveUnavailableRuns"] == 2
    # A run without a clear reading keeps the count; a paused/unclear page too.
    daily.track_unavailable_runs([], "t3", path)
    daily.track_unavailable_runs([reading("review_required", "t4")], "t4", path)
    out = daily.track_unavailable_runs([reading("unavailable", "t5")], "t5", path)
    assert out[0]["consecutiveUnavailableRuns"] == 3
    daily.track_unavailable_runs([reading("parsed", "t6")], "t6", path)
    out = daily.track_unavailable_runs([reading("unavailable", "t7")], "t7", path)
    assert out[0]["consecutiveUnavailableRuns"] == 1


def test_broken_count_file_never_enables_retirement(tmp_path, capsys):
    path = tmp_path / "offer_unavailable_runs.json"
    path.write_text("{broken", encoding="utf-8")
    out = daily.track_unavailable_runs([reading("unavailable", "t1")], "t1", path)
    assert "consecutiveUnavailableRuns" not in out[0]
    assert path.read_text(encoding="utf-8") == "{broken"
    assert "ended-offer counts not updated" in capsys.readouterr().out


def test_validator_accepts_only_confirmed_retirements(tmp_path):
    import json
    base = {"source": "warau", "publicationMode": "confirmed_unavailable_retirement",
            "retired": True, "updated": True}
    decisions = [dict(base, offerKey="ok", consecutiveUnavailableRuns=3),
                 dict(base, offerKey="early", consecutiveUnavailableRuns=2),
                 dict(base, offerKey="moppy", source="moppy", consecutiveUnavailableRuns=3),
                 dict(base, offerKey="held", consecutiveUnavailableRuns=3, holdReason="x")]
    (tmp_path / "data").mkdir()
    (tmp_path / "data/daily_scan_review.json").write_text(
        json.dumps({"existingPublication": {"decisions": decisions}}), encoding="utf-8")
    assert validator.reviewed_retirement_keys(tmp_path) == {"ok"}


def test_workflow_commits_the_count_file_and_build_keeps_it_private():
    workflow = (ROOT / ".github/workflows/refresh-verified-offers.yml").read_text(encoding="utf-8")
    assert "git add data/offer_unavailable_runs.json" in workflow
    assert "offer_unavailable_runs" not in (ROOT / "scripts/build_public_site.py").read_text(encoding="utf-8")
