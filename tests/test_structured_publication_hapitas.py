import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import structured_publication as publication

NOW = "2026-09-15T16:17:00+00:00"
URL = "https://hapitas.jp/item/detail/itemid/101445"
SOURCES = {"hapitas": {"id": "hapitas", "search_domains": ["hapitas.jp"]}}
POLICY = {"enabled": True, "sources": ["hapitas"]}


def markup(reward="12,345"):
    return f'''<!doctype html>
<html><head><link rel="canonical" href="{URL}"></head><body>
<h1>テストゲーム Android</h1>
<div>1ポイント=1円</div>
<div>{reward} pt ポイント対象条件
ポイント獲得条件 新規アプリインストール後に指定条件を達成
成果受付期限 60日以内
ハピタスご利用前に必ずご確認ください</div>
</body></html>'''


def sample():
    evidence = publication.direct.inspect_hapitas_offer(markup(), URL, URL, ["テストゲーム"])
    assert evidence["state"] == "parsed"
    item = {
        "source": "hapitas",
        "game": "テストゲーム",
        "url": URL,
        "checkedAt": NOW,
        "sourceEvidence": evidence,
    }
    row = {
        "offerKey": "test-hapitas",
        "game": "テストゲーム",
        "site": "hapitas",
        "provider": "",
        "url": URL,
        "sourceUrl": URL,
        "reward": "10000",
        "type": "StepUp",
        "condition": "既存の確認済み条件は保持する",
        "deadline": "既存期限も保持する",
        "platform": "Android",
        "verified": "true",
        "updatedAt": "2026-09-01",
    }
    return row, item


def test_hapitas_review_only_reward_never_updates_publication():
    row, item = sample()
    updated, report = publication.prepare([row], [item], SOURCES, NOW, POLICY)
    assert updated == [row]
    assert updated[0]["condition"] == row["condition"]
    assert updated[0]["deadline"] == row["deadline"]
    assert updated[0]["type"] == row["type"]
    assert updated[0]["platform"] == "Android"
    assert report["rewardChanges"] == 0
    assert report["updatedRows"] == 0


def test_hapitas_tampered_fingerprint_holds_old_row():
    row, item = sample()
    item["sourceEvidence"]["evidenceFingerprint"] = "tampered"
    updated, report = publication.prepare([row], [item], SOURCES, NOW, POLICY)
    assert updated == [row]
    assert report["updatedRows"] == 0
    assert report["heldRows"] == 1


def test_hapitas_platform_mismatch_holds_old_row():
    row, item = sample()
    row = copy.deepcopy(row)
    row["platform"] = "iOS"
    updated, report = publication.prepare([row], [item], SOURCES, NOW, POLICY)
    assert updated == [row]
    assert report["updatedRows"] == 0
    assert report["heldRows"] == 1


def test_hapitas_stale_evidence_holds_old_row():
    row, item = sample()
    item["checkedAt"] = "2026-09-14T16:17:00+00:00"
    updated, report = publication.prepare([row], [item], SOURCES, NOW, POLICY)
    assert updated == [row]
    assert report["updatedRows"] == 0
    assert report["heldRows"] == 1
