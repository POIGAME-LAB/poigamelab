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
