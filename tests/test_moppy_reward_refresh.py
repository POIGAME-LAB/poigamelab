import csv
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "moppy_reward_refresh", ROOT / "scripts" / "moppy_reward_refresh.py"
)
moppy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(moppy)

FIELDS = [
    "offerKey", "game", "site", "provider", "reward", "condition", "platform",
    "type", "deadline", "updatedAt", "url", "sourceUrl", "verified",
]
CHECKED = "2026-09-17T01:00:00+00:00"


def evidence(reward=700, platform="Android", offer_id="12345"):
    value = {
        "state": "parsed",
        "parserVersion": "moppy-shell-review-v1",
        "offerId": offer_id,
        "name": "テストゲーム（StepUp）",
        "platform": platform,
        "displayedRewardPoints": reward,
        "rewardUnit": "P",
        "baseYenPerPoint": 1,
        "downstreamTermsRequired": True,
        "headerText": f"テストゲーム（StepUp） {reward}P",
        "termsText": "ポイント獲得条件 成果受付期間 注意事項",
    }
    payload = {field: value[field] for field in moppy.FINGERPRINT_FIELDS}
    value["evidenceFingerprint"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return value


def configure(tmp_path, monkeypatch, *, reward="600", platform="Android",
              evidence_value=None, checked_at=CHECKED, duplicate=False):
    data = tmp_path / "data"
    data.mkdir()
    paths = {
        "PUBLISHED": data / "published_offers.csv",
        "REVIEW": data / "comparison_review_queue.json",
        "STATUS": data / "comparison_refresh_status.json",
        "DAILY": data / "daily_scan_review.json",
        "SNAPSHOT": data / "unified_offer_snapshot.json",
    }
    for name, path in paths.items():
        monkeypatch.setattr(moppy, name, path)

    row = {
        "offerKey": "moppy-test",
        "game": "テストゲーム",
        "site": "moppy",
        "provider": "",
        "reward": reward,
        "condition": "KEEP CONDITION",
        "platform": platform,
        "type": "StepUp",
        "deadline": "KEEP DEADLINE",
        "updatedAt": "2026-09-01",
        "url": "https://pc.moppy.jp/ad/detail.php?site_id=12345",
        "sourceUrl": "https://pc.moppy.jp/ad/detail.php?site_id=12345",
        "verified": "true",
    }
    rows = [row]
    if duplicate:
        rows.append(dict(row, offerKey="duplicate"))
    with paths["PUBLISHED"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    e = evidence_value or evidence()
    review = {
        "items": [{
            "game": "テストゲーム",
            "source": "moppy",
            "url": "https://pc.moppy.jp/ad/detail.php?s_id=12345",
            "reason": "structured_offer_review_required",
            "sourceEvidence": e,
            "checkedAt": checked_at,
            "storedPlatform": platform,
            "storedReward": reward,
            "platformMatches": e["platform"] == platform,
            "approvalHoldReason": "source_refresh_not_enabled",
        }]
    }
    paths["REVIEW"].write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    paths["STATUS"].write_text(json.dumps({
        "checkedAt": CHECKED,
        "publishedRewardChanges": 2,
        "refreshedRows": 3,
    }), encoding="utf-8")
    paths["DAILY"].write_text(json.dumps({"checkedAt": CHECKED}), encoding="utf-8")
    paths["SNAPSHOT"].write_text(json.dumps({
        "groups": [{
            "game": "テストゲーム",
            "offers": [{
                "source": "moppy",
                "url": "https://pc.moppy.jp/ad/detail.php?site_id=12345",
                "rewardYen": None,
                "rewardVerified": False,
                "parserVersion": "moppy-shell-review-v1",
            }],
            "verifiedRewardCount": 0,
            "maxVerifiedRewardYen": None,
        }]
    }, ensure_ascii=False), encoding="utf-8")
    return paths


def published(paths):
    with paths["PUBLISHED"].open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_safe_moppy_reward_only_update_preserves_all_prose_and_enriches_snapshot(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch)
    assert moppy.main() == 0

    row = published(paths)[0]
    assert row["reward"] == "700"
    assert row["condition"] == "KEEP CONDITION"
    assert row["deadline"] == "KEEP DEADLINE"
    assert row["type"] == "StepUp"
    assert row["updatedAt"] == "2026-09-17"
    assert row["url"] == "https://pc.moppy.jp/ad/detail.php?site_id=12345"
    assert row["sourceUrl"] == "https://pc.moppy.jp/ad/detail.php?s_id=12345"

    status = json.loads(paths["STATUS"].read_text(encoding="utf-8"))
    assert status["publishedRewardChanges"] == 3
    assert status["refreshedRows"] == 4
    assert status["moppyRewardOnly"]["networkCalls"] == 0
    assert status["moppyRewardOnly"]["newRowsCreated"] == 0
    assert status["moppyRewardOnly"]["conditionsChanged"] == 0

    snapshot = json.loads(paths["SNAPSHOT"].read_text(encoding="utf-8"))
    offer = snapshot["groups"][0]["offers"][0]
    assert offer["rewardYen"] == 700
    assert offer["rewardVerified"] is True
    assert snapshot["groups"][0]["verifiedRewardCount"] == 1
    assert snapshot["groups"][0]["maxVerifiedRewardYen"] == 700


def test_same_reward_refreshes_date_without_counting_reward_change(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch, reward="700")
    assert moppy.main() == 0
    row = published(paths)[0]
    assert row["reward"] == "700"
    assert row["updatedAt"] == "2026-09-17"
    status = json.loads(paths["STATUS"].read_text())
    assert status["moppyRewardOnly"]["verifiedRows"] == 1
    assert status["moppyRewardOnly"]["rewardChanges"] == 0


def test_unknown_stored_platform_is_allowed_only_by_exact_unique_offer_identity(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch, platform="不明")
    assert moppy.main() == 0
    assert published(paths)[0]["reward"] == "700"


def test_known_platform_mismatch_is_held(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch, platform="iOS")
    review = json.loads(paths["REVIEW"].read_text())
    review["items"][0]["sourceEvidence"] = evidence(platform="Android")
    review["items"][0]["platformMatches"] = False
    paths["REVIEW"].write_text(json.dumps(review, ensure_ascii=False))
    assert moppy.main() == 0
    assert published(paths)[0]["reward"] == "600"
    status = json.loads(paths["STATUS"].read_text())
    assert status["moppyRewardOnly"]["heldItems"] == 1


def test_fingerprint_tampering_is_held(tmp_path, monkeypatch):
    e = evidence()
    e["displayedRewardPoints"] = 999
    paths = configure(tmp_path, monkeypatch, evidence_value=e)
    assert moppy.main() == 0
    assert published(paths)[0]["reward"] == "600"


def test_stale_review_is_held(tmp_path, monkeypatch):
    paths = configure(
        tmp_path, monkeypatch, checked_at="2026-09-16T01:00:00+00:00"
    )
    assert moppy.main() == 0
    assert published(paths)[0]["reward"] == "600"


def test_duplicate_published_offer_identity_is_held(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch, duplicate=True)
    assert moppy.main() == 0
    assert [row["reward"] for row in published(paths)] == ["600", "600"]


def test_nightly_workflow_uses_same_scan_then_snapshot_then_moppy_gate_before_history():
    workflow = (
        ROOT / ".github" / "workflows" / "refresh-verified-offers.yml"
    ).read_text(encoding="utf-8")
    scan = "run: python scripts/daily_scan_review.py"
    snapshot = "run: python scripts/unified_offer_snapshot.py"
    moppy_gate = "run: python scripts/moppy_reward_refresh.py"
    history = "run: python scripts/append_offer_history.py"
    assert workflow.count(scan) == 1
    assert workflow.count(snapshot) == 1
    assert workflow.count(moppy_gate) == 1
    assert workflow.index(scan) < workflow.index(snapshot) < workflow.index(moppy_gate) < workflow.index(history)
