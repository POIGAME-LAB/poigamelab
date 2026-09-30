import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import daily_scan_review  # noqa: E402
import direct_offer_refresh as direct  # noqa: E402
import verified_offer_urls as vou  # noqa: E402
from tests.test_direct_offer_refresh_v1 import warau_markup  # noqa: E402,F401
from tests.test_structured_publication import sample  # noqa: E402
from tests.test_verified_existing_publication import envelope, run  # noqa: E402

WARAU = "https://www.warau.jp/contents/point/pointEntrance.php?point_id="


def decision(point_id, game="クロンダイクの冒険", **extra):
    url = WARAU + str(point_id)
    d = {"game": game, "source": "warau", "identity": direct.offer_identity_key(url, "warau"),
         "url": url, "publicationEligible": True, "updated": True, "added": False}
    d.update(extra)
    return d


def test_only_gate_eligible_decisions_are_registered():
    held = decision(2, holdReason="incomplete_parser_contract", publicationEligible=None)
    not_eligible = decision(3, publicationEligible=None)
    entries, changed = vou.register([], [decision(1), held, not_eligible], "2026-09-30T01:17:00+09:00")
    assert changed
    assert [e["url"] for e in entries] == [WARAU + "1"]
    assert entries[0]["firstVerifiedAt"] == entries[0]["lastVerifiedAt"] == "2026-09-30T01:17:00+09:00"


def test_identity_mismatch_or_missing_url_is_not_registered():
    wrong = decision(1)
    wrong["identity"] = "warau:point_id:999"
    missing = decision(2)
    missing["url"] = None
    entries, changed = vou.register([], [wrong, missing], "t1")
    assert entries == [] and not changed


def test_reverification_updates_last_seen_without_duplicates():
    entries, _ = vou.register([], [decision(1)], "t1")
    # Same offer seen again with the category query suffix Warau adds.
    again = decision(1)
    again["url"] = WARAU + "1&pl=pc_categoryService"
    entries, changed = vou.register(entries, [again], "t2")
    assert changed and len(entries) == 1
    assert entries[0]["firstVerifiedAt"] == "t1" and entries[0]["lastVerifiedAt"] == "t2"
    entries, changed = vou.register(entries, [again], "t2")
    assert not changed


def test_save_load_round_trip_and_corrupt_file_is_not_overwritten(tmp_path, capsys):
    path = tmp_path / "verified_offer_urls.json"
    assert vou.load(path) == []
    daily_scan_review.remember_verified_urls([decision(1)], "t1", path=path)
    assert [e["url"] for e in vou.load(path)] == [WARAU + "1"]

    path.write_text("{broken", encoding="utf-8")
    daily_scan_review.remember_verified_urls([decision(2)], "t2", path=path)
    assert path.read_text(encoding="utf-8") == "{broken"
    assert "verified offer URLs not updated" in capsys.readouterr().out
    with pytest.raises(ValueError):
        vou.load(path)


def test_merge_adds_urls_to_known_targets_only():
    targets = [
        {"game": "クロンダイクの冒険", "aliases": ["クロンダイクの冒険"],
         "known_urls_by_source": {"warau": [WARAU + "1"]}},
        {"game": "Merge Help: ホームデザインパズル", "aliases": [], "known_urls_by_source": {}},
    ]
    entries = [
        {"game": "クロンダイクの冒険", "source": "warau", "url": WARAU + "1&pl=pc_categoryService"},
        {"game": "クロンダイクの冒険", "source": "warau", "url": WARAU + "5"},
        {"game": "Merge Help: ホームデザインパズル", "source": "warau", "url": WARAU + "7"},
        {"game": "削除済みゲーム", "source": "warau", "url": WARAU + "9"},
    ]
    vou.merge_into_targets(targets, entries)
    assert targets[0]["known_urls_by_source"]["warau"] == [WARAU + "1", WARAU + "5"]
    assert targets[1]["known_urls_by_source"]["warau"] == [WARAU + "7"]
    assert len(targets) == 2


def test_nightly_workflow_commits_the_list():
    workflow = (ROOT / ".github/workflows/refresh-verified-offers.yml").read_text(encoding="utf-8")
    assert "git add data/verified_offer_urls.json" in workflow


def test_list_stays_out_of_the_public_build():
    builder = (ROOT / "scripts" / "build_public_site.py").read_text(encoding="utf-8")
    assert "verified_offer_urls" not in builder


def test_strict_gate_decision_carries_url_and_only_passing_offers_register(warau_markup):
    _, item = sample(warau_markup)
    out, report = run([], [envelope(item)])
    passed = report["decisions"][0]
    assert passed["publicationEligible"] is True and passed["url"] == out[0]["url"]
    entries, changed = vou.register([], report["decisions"], "t1")
    assert changed and [e["url"] for e in entries] == [out[0]["url"]]

    _, held = run([], [envelope(item)], catalog={"別のゲーム"})
    assert "holdReason" in held["decisions"][0]
    assert vou.register([], held["decisions"], "t1") == ([], False)


ENDED_PAGE = """<html><head><title>ポイ活ならワラウ - 初心者でも貯まりやすいポイントサイト</title>
<link rel="canonical" href="https://www.warau.jp/contents/point/pointEntrance.php?point_id=204347" />
</head><body><div class="commonError-Body"><div class="sw-frameMessage commonError-frameMessage">
<p class="commonError-Paragraph">こちらのページは表示できません</p></div>
<a href="/" class="commonError-BtnBack">ワラウホームへ戻る</a></div></body></html>"""


def reading(point_id, state, checked_at, game="クロンダイクの冒険"):
    evidence = {"state": state}
    if state == "unavailable":
        evidence.update(reason="source_offer_unavailable", offerId=str(point_id))
    return {"origin": "current_first_party_detail", "game": game, "source": "warau",
            "requestedUrl": WARAU + str(point_id), "url": WARAU + str(point_id),
            "sourceEvidence": evidence, "checkedAt": checked_at}


def test_warau_ended_error_page_is_read_as_unavailable():
    url = WARAU + "204347"
    evidence = direct.inspect_warau_offer(ENDED_PAGE, url, url, ["ロックンキャッシュカジノ"])
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "source_offer_unavailable"
    assert evidence["offerId"] == "204347"
    # The same error body for a different offer id is not this offer ending.
    other = WARAU + "999"
    assert direct.inspect_warau_offer(ENDED_PAGE, other, other, ["x"])["state"] == "review_required"


def test_url_is_removed_only_after_three_runs_that_read_the_offer_as_ended():
    entries, _ = vou.register([], [decision(1), decision(2)], "t0")
    for run, checked_at in enumerate(("t1", "t2"), 1):
        entries, changed, removed = vou.retire(entries, [reading(1, "unavailable", checked_at)], checked_at)
        assert changed and not removed
        assert entries[0]["unavailableStreak"] == run
    # A second pass over the same run never double counts.
    entries, changed, _ = vou.retire(entries, [reading(1, "unavailable", "t2")], "t2")
    assert not changed and entries[0]["unavailableStreak"] == 2
    entries, changed, removed = vou.retire(entries, [reading(1, "unavailable", "t3")], "t3")
    assert [e["url"] for e in removed] == [WARAU + "1"]
    assert [e["url"] for e in entries] == [WARAU + "2"]


@pytest.mark.parametrize("snapshots", [
    [],  # page not opened this run (fetch error, budget)
    [reading(1, "review_required", "t2")],  # parser doubt is not "ended"
    [reading(1, "unavailable", "t2"), reading(1, "review_required", "t2")],  # conflicting readings
    [reading(1, "unavailable", "stale")],  # a reading from another run
    [reading(1, "unavailable", "t2", game="別のゲーム")],  # another game's reading
])
def test_missing_or_unclear_readings_never_count_toward_removal(snapshots):
    entries, _ = vou.register([], [decision(1)], "t0")
    entries, _, _ = vou.retire(entries, [reading(1, "unavailable", "t1")], "t1")
    entries, changed, removed = vou.retire(entries, snapshots, "t2")
    assert not changed and not removed
    assert entries[0]["unavailableStreak"] == 1


def test_live_reading_restarts_the_count():
    entries, _ = vou.register([], [decision(1)], "t0")
    entries, _, _ = vou.retire(entries, [reading(1, "unavailable", "t1")], "t1")
    entries, changed, _ = vou.retire(entries, [reading(1, "parsed", "t2")], "t2")
    assert changed and "unavailableStreak" not in entries[0] and "lastUnavailableAt" not in entries[0]
    entries, _, _ = vou.retire(entries, [reading(1, "unavailable", "t1")], "t1")
    entries, changed = vou.register(entries, [decision(1)], "t3")
    assert changed and "unavailableStreak" not in entries[0]


def test_nightly_hook_saves_the_count_and_drops_the_ended_url(tmp_path, capsys):
    path = tmp_path / "verified_offer_urls.json"
    daily_scan_review.remember_verified_urls([decision(1), decision(2)], "t0", path=path)
    for checked_at in ("t1", "t2", "t3"):
        daily_scan_review.remember_verified_urls(
            [], checked_at, path=path, snapshots=[reading(1, "unavailable", checked_at)])
    assert [e["url"] for e in vou.load(path)] == [WARAU + "2"]
    assert "ended offer URL removed from recheck list" in capsys.readouterr().out


def test_ended_reading_holds_the_published_row_instead_of_deleting_it(warau_markup):
    row, item = sample(warau_markup)
    ended = dict(item, sourceEvidence={"state": "unavailable", "reason": "source_offer_unavailable",
                                       "offerId": "101"})
    out, report = run([row], [envelope(ended)])
    assert out == [row]
    assert report["decisions"][0].get("holdReason")
