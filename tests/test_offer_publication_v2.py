"""Publication rules decided by the operator on 2026-11-24 (offline, actual parsers).

* A Moppy StepUp page that shows only its total (Steps behind "POINT GET") is published with the
  verified total and an explicit note, instead of keeping an old total forever.
* Nothing else is relaxed: provider/downstream offers of other kinds, unknown OS and fingerprint
  tampering still hold the row.
"""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import structured_publication as pub  # noqa: E402
from tests.test_direct_offer_refresh_v1 import moppy_markup, MOPPY_URL  # noqa: E402,F401

NOW = "2026-11-23T21:53:06+00:00"
POLICY = {"enabled": True, "sources": ["warau", "coincome", "moppy", "hapitas", "point_town", "ec_navi", "amefuri"],
          "verifiedExistingGameGate": True, "allowVerifiedExistingGameNewRows": True}
SOURCES = {"moppy": {"id": "moppy", "search_domains": ["pc.moppy.jp"]}}
GAME = "テストゲーム"


def _item(raw):
    e = pub.direct.inspect_moppy_offer(raw, MOPPY_URL, MOPPY_URL, [GAME])
    assert e["state"] == "parsed", e
    return {"source": "moppy", "game": GAME, "url": MOPPY_URL, "sourceEvidence": e, "checkedAt": NOW,
            "origin": "current_first_party_detail", "requestedUrl": MOPPY_URL}


def _row(reward="23367"):
    return {"offerKey": "k", "game": GAME, "site": "moppy", "provider": "", "url": MOPPY_URL, "sourceUrl": MOPPY_URL,
            "reward": reward, "condition": "以前の条件", "platform": "Android", "type": "StepUp", "deadline": "以前",
            "verified": "true", "updatedAt": "2026-09-28"}


def _run(rows, items):
    return pub.prepare_verified(rows, items, SOURCES, NOW, POLICY, {GAME}, [], True)


def test_stale_moppy_stepup_total_is_refreshed_with_the_total_only_note(moppy_markup):
    out, report = _run([_row()], [_item(moppy_markup)])
    assert "holdReason" not in report["decisions"][0], report
    row = out[0]
    assert row["reward"] == "600" and row["updatedAt"] == "2026-11-24" and row["type"] == "StepUp"
    assert pub.MOPPY_TOTAL_ONLY_NOTE in row["condition"] and "45日以内" in row["condition"]
    assert report["rewardChanges"] == 1 and report["updatedRows"] == 1


def test_new_moppy_stepup_row_carries_the_note_too(moppy_markup):
    out, report = _run([], [_item(moppy_markup)])
    assert report["addedRows"] == 1 and pub.MOPPY_TOTAL_ONLY_NOTE in out[0]["condition"]
    again, report2 = _run(out, [_item(moppy_markup)])
    assert again == out and report2["updatedRows"] == 0  # note is not appended twice


def test_moppy_page_without_stepup_wording_still_needs_its_own_terms(moppy_markup):
    raw = moppy_markup.replace("（StepUp）", "").replace("各成果地点クリア", "レベル10クリア").replace("各成果地点は", "詳細は")
    item = _item(raw)
    assert item["sourceEvidence"]["downstreamTermsRequired"] is True
    out, report = _run([_row()], [item])
    assert out[0]["reward"] == "23367" and report["decisions"][0]["holdReason"] == "downstream_or_provider_contract_required"


@pytest.mark.parametrize("defect", ["provider", "os", "fingerprint", "steps"])
def test_other_contract_checks_are_not_relaxed(moppy_markup, defect):
    item = _item(moppy_markup)
    e = item["sourceEvidence"]
    if defect == "provider":
        e["providerCandidates"] = ["SKYFLAG"]
    elif defect == "os":
        e["platform"] = ""
    elif defect == "fingerprint":
        e["verifiedCurrentRewardYen"] = 999
    else:
        e["stepRewardPoints"] = [100, 500]
    before = copy.deepcopy(_row())
    out, report = _run([_row()], [item])
    assert out == [before] and "holdReason" in report["decisions"][0]


def test_helper_is_moppy_only(moppy_markup):
    e = _item(moppy_markup)["sourceEvidence"]
    assert pub.moppy_stepup_total_only("moppy", e) is True
    assert pub.moppy_stepup_total_only("hapitas", e) is False
    assert pub.moppy_stepup_total_only("moppy", {**e, "downstreamTermsRequired": False}) is False


def test_publication_hold_summary_counts_sites_and_reasons_without_urls():
    import daily_scan_review as daily
    decisions = [
        {"source": "moppy", "holdReason": "complete_step_conditions_required", "url": "https://pc.moppy.jp/x"},
        {"source": "moppy", "holdReason": "complete_step_conditions_required"},
        {"source": "moppy", "updated": True},
        {"source": "hapitas", "holdReason": "reviewed_platform_authorization_required"},
        "not-a-dict",
    ]
    out = daily.summarize_publication_holds(decisions)
    assert out == {
        "hapitas": {"published": 0, "held": 1, "holdReasons": {"reviewed_platform_authorization_required": 1}},
        "moppy": {"published": 1, "held": 2, "holdReasons": {"complete_step_conditions_required": 2}},
    }
    assert "http" not in str(out)
    assert daily.summarize_publication_holds(None) == {}


def test_moppy_s_id_and_site_id_are_one_offer(moppy_markup):
    """2026-11-24: the catalog URL (?s_id=N&track_ref=category) created a second row for the same offer."""
    a = "https://pc.moppy.jp/ad/detail.php?site_id=12345"
    b = "https://pc.moppy.jp/ad/detail.php?s_id=12345&track_ref=category"
    assert pub.direct.offer_identity_key(a, "moppy") == pub.direct.offer_identity_key(b, "moppy") == "moppy:site_id:12345"
    # other sites keep their own key names
    assert pub.direct.offer_identity_key("https://www.warau.jp/contents/point/pointEntrance.php?point_id=1", "warau") == "warau:point_id:1"
    item = _item(moppy_markup.replace("site_id=12345", "s_id=12345&amp;track_ref=category"))
    item["url"] = item["requestedUrl"] = b
    out, report = _run([_row()], [item])
    assert len(out) == 1 and report["addedRows"] == 0 and out[0]["reward"] == "600", report
