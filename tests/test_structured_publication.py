import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import structured_publication as publication
from tests.test_direct_offer_refresh_v1 import (
    warau_markup, WARAU_URL, chobi_markup, CHOBI_URL,
    coincome_markup, COINCOME_URL, _hapitas_fixture,
)

NOW = "2026-09-15T16:17:00+00:00"
SOURCES = {"warau": {"id": "warau", "search_domains": ["www.warau.jp"]}}
POLICY = {"enabled": True, "sources": ["warau"]}


def sample(markup):
    evidence = publication.direct.inspect_warau_offer(markup, WARAU_URL, WARAU_URL, ["テストゲーム"])
    item = {"source": "warau", "game": "テストゲーム", "url": WARAU_URL,
            "checkedAt": NOW, "sourceEvidence": evidence}
    row = {"offerKey": "test", "game": "テストゲーム", "site": "warau", "provider": "",
           "url": WARAU_URL, "sourceUrl": WARAU_URL, "reward": "123", "type": "StepUp",
           "condition": "以前の条件", "deadline": "以前の期限", "platform": "iOS",
           "verified": "true", "updatedAt": "2026-09-01"}
    return row, item


def test_actual_parser_to_publication_updates_amount_conditions_and_jst_date(warau_markup):
    row, item = sample(warau_markup)
    updated, report = publication.prepare([row], [item], SOURCES, NOW, POLICY, True)
    assert updated[0]["reward"] == "300"
    assert "10日以内にレベル5到達" in updated[0]["condition"]
    assert "20日以内にレベル10到達" in updated[0]["condition"]
    assert "新規利用のみ" in updated[0]["condition"]
    assert "999,999" not in updated[0]["condition"]
    assert updated[0]["updatedAt"] == "2026-09-16"
    assert row["reward"] == "123"  # prepare does not mutate the source
    assert report["updatedRows"] == report["rewardChanges"] == 1
    same, again = publication.prepare(updated, [item], SOURCES, NOW, POLICY, True)
    assert same == updated and again["updatedRows"] == 0


@pytest.mark.parametrize("location", ["item", "sourceEvidence", "evidence"])
def test_valid_snapshot_with_explicit_publication_veto_never_updates(warau_markup, location):
    row, item = sample(warau_markup)
    if location == "item":
        item["publicationAuthorized"] = False
    else:
        item.setdefault(location, {})["publicationAuthorized"] = False
    updated, report = publication.prepare([row], [item], SOURCES, NOW, POLICY, True)
    assert updated == [row]
    assert report["rewardChanges"] == report["updatedRows"] == 0
    assert report["decisions"][0]["holdReason"] == "no_current_evidence"


@pytest.mark.parametrize("change", ["stale", "rate", "os", "fingerprint", "total", "terms", "paid", "duplicate", "empty", "unverified", "disabled"])
def test_invalid_snapshot_keeps_old_row(warau_markup, change):
    row, item = sample(warau_markup)
    rate, policy = True, POLICY
    items = [item]
    if change == "stale": item["checkedAt"] = "2026-01-01"
    if change == "rate": rate = False
    if change == "os": row["platform"] = "Android"
    if change == "fingerprint": item["sourceEvidence"]["evidenceFingerprint"] = "wrong"
    if change == "total": item["sourceEvidence"]["rewardPoints"] = 400
    if change == "terms": item["sourceEvidence"]["termsText"] = "partial"
    if change == "paid": row["provider"] = "unknown provider"
    if change == "duplicate": items.append({**item, "sourceEvidence": {}})
    if change == "empty": items = []
    if change == "unverified": row["verified"] = "false"
    if change == "disabled": policy = {"enabled": False}
    updated, report = publication.prepare([row], items, SOURCES, NOW, policy, rate)
    assert updated == [row] and report["updatedRows"] == 0


def test_duplicate_published_identity_is_held(warau_markup):
    row, item = sample(warau_markup)
    rows = [row, {**row, "offerKey": "second"}]
    updated, report = publication.prepare(rows, [item], SOURCES, NOW, POLICY, True)
    assert updated == rows and report["heldRows"] == 2


def test_partial_failure_merges_only_good_rows(warau_markup):
    row, item = sample(warau_markup)
    other = {**row, "offerKey": "other", "url": WARAU_URL.replace("101", "102")}
    updated, report = publication.prepare([row, other], [item], SOURCES, NOW, POLICY, True)
    assert updated[0]["reward"] == "300" and updated[1] == other
    assert report["updatedRows"] == 1 and report["heldRows"] == 1


def test_paid_step_is_not_omitted(warau_markup):
    raw = warau_markup.replace("20日以内にレベル10到達", "20日以内に初回課金800円")
    row, item = sample(raw)
    result, _ = publication.prepare([row], [item], SOURCES, NOW, POLICY, True)
    assert "初回課金800円" in result[0]["condition"]


def test_chobirich_requires_explicit_yen_and_preserves_paid_step_and_exclusions(chobi_markup):
    source = {"chobirich": {"id": "chobirich", "search_domains": ["www.chobirich.com"]}}
    evidence = publication.direct.inspect_chobirich_offer(chobi_markup, CHOBI_URL, CHOBI_URL, ["テストゲーム"])
    item = {"source": "chobirich", "url": CHOBI_URL, "checkedAt": NOW, "sourceEvidence": evidence}
    result = publication.snapshot(item, source, NOW)
    assert result["reward"] == "600" and result["platform"] == "Android"
    assert "一括3200円課金" in result["condition"]
    assert "却下条件" in result["condition"]
    item["sourceEvidence"] = publication.direct.inspect_chobirich_offer(
        chobi_markup.replace("円相当", "円"), CHOBI_URL, CHOBI_URL, ["テストゲーム"])
    with pytest.raises(publication.Hold): publication.snapshot(item, source, NOW)


def test_coincome_v2_reward_only_snapshot_updates_reward_and_preserves_old_terms(coincome_markup):
    sources = {
        "coincome": {
            "id": "coincome",
            "search_domains": ["cimcome.jp"],
        }
    }
    policy = {"enabled": True, "sources": ["coincome"]}
    evidence = publication.direct.inspect_coincome_offer(
        coincome_markup, COINCOME_URL, COINCOME_URL, ["テストゲーム"]
    )
    assert evidence["state"] == "parsed"
    assert evidence["parserVersion"] == "coincome-detail-review-v2"
    row = {
        "offerKey": "coincome-test",
        "game": "テストゲーム",
        "site": "coincome",
        "provider": "",
        "url": COINCOME_URL,
        "sourceUrl": COINCOME_URL,
        "reward": "500",
        "type": "StepUp",
        "condition": "既存の公開条件",
        "deadline": "既存の公開期限",
        "platform": "Android",
        "verified": "true",
        "updatedAt": "2026-09-01",
    }
    item = {
        "source": "coincome",
        "game": "テストゲーム",
        "url": COINCOME_URL,
        "checkedAt": NOW,
        "sourceEvidence": evidence,
    }
    updated, report = publication.prepare([row], [item], sources, NOW, policy)
    assert updated[0]["reward"] == "600"
    assert updated[0]["platform"] == "Android"
    assert updated[0]["condition"] == "既存の公開条件"
    assert updated[0]["deadline"] == "既存の公開期限"
    assert updated[0]["updatedAt"] == "2026-09-16"
    assert report["updatedRows"] == 1
    assert report["rewardChanges"] == 1
    assert report["decisions"][0]["publicationMode"] == "reward_only"


def test_hapitas_v2_reward_only_snapshot_accepts_reviewed_registry_platform():
    url = "https://hapitas.jp/item/detail/itemid/102497/"
    sources = {"hapitas": {"id": "hapitas", "search_domains": ["hapitas.jp"]}}
    policy = {"enabled": True, "sources": ["hapitas"]}
    evidence = publication.direct.inspect_hapitas_offer(
        _hapitas_fixture(), url, url, ["Mistplay"],
        reviewed_platform="iOS", publication_authorized=True,
    )
    assert evidence["state"] == "parsed"
    assert evidence["platformProvenance"] == "reviewed_offer_registry"
    row = {
        "offerKey": f"Mistplay|hapitas|iOS|{url}",
        "game": "Mistplay", "site": "hapitas", "provider": "",
        "url": url, "sourceUrl": url, "reward": "9000",
        "type": "StepUp", "condition": "既存条件", "deadline": "既存期限",
        "platform": "iOS", "verified": "true", "updatedAt": "2026-09-01",
    }
    item = {
        "source": "hapitas", "game": "Mistplay", "url": url,
        "checkedAt": NOW, "sourceEvidence": evidence,
    }
    updated, report = publication.prepare([row], [item], sources, NOW, policy)
    assert updated[0]["reward"] == "9351"
    assert updated[0]["condition"] == "既存条件"
    assert updated[0]["deadline"] == "既存期限"
    assert report["updatedRows"] == 1
    assert report["rewardChanges"] == 1
    assert report["retiredRows"] == 0


def test_hapitas_v2_accepts_source_title_platform_only_when_registry_authorized():
    url = "https://hapitas.jp/item/detail/itemid/102497/"
    sources = {"hapitas": {"id": "hapitas", "search_domains": ["hapitas.jp"]}}
    policy = {"enabled": True, "sources": ["hapitas"]}
    raw = _hapitas_fixture().replace(
        "<h1>Mistplay</h1>", "<h1>Mistplay（iOS）</h1>"
    )
    evidence = publication.direct.inspect_hapitas_offer(
        raw, url, url, ["Mistplay"],
        reviewed_platform="iOS", publication_authorized=True,
    )
    assert evidence["state"] == "parsed"
    assert evidence["platform"] == "iOS"
    assert evidence["platformProvenance"] == "source_title"
    assert evidence["publicationAuthorized"] is True
    item = {
        "source": "hapitas", "game": "Mistplay", "url": url,
        "checkedAt": NOW, "sourceEvidence": evidence,
    }
    snap = publication.reward_only_snapshot(item, sources, NOW)
    assert snap["reward"] == "9351"
    assert snap["platform"] == "iOS"


def test_hapitas_explicit_ended_page_retires_exact_published_row():
    url = "https://hapitas.jp/item/detail/itemid/101355"
    sources = {"hapitas": {"id": "hapitas", "search_domains": ["hapitas.jp"]}}
    policy = {"enabled": True, "sources": ["hapitas"]}
    raw = """
    <html><head>
      <link rel="canonical" href="https://hapitas.jp/item/detail/itemid/101355/">
    </head><body>
      <h1>キングショット</h1>
      <div>キングショット この広告は終了しています</div>
      <section>ポイント対象条件 STEP1: 役場レベル4に到達で42pt</section>
    </body></html>
    """
    evidence = publication.direct.inspect_hapitas_offer(
        raw, url, url, ["キングショット"],
        reviewed_platform="Android", publication_authorized=True,
    )
    row = {
        "offerKey": f"キングショット|hapitas|Android|{url}",
        "game": "キングショット", "site": "hapitas", "provider": "",
        "url": url, "sourceUrl": url, "reward": "16320",
        "type": "StepUp", "condition": "既存条件", "deadline": "既存期限",
        "platform": "Android", "verified": "true", "updatedAt": "2026-09-01",
    }
    item = {
        "source": "hapitas", "game": "キングショット", "url": url,
        "checkedAt": NOW, "sourceEvidence": evidence,
    }
    updated, report = publication.prepare([row], [item], sources, NOW, policy)
    assert updated == []
    assert report["retiredRows"] == 1
    assert report["updatedRows"] == 1
    assert report["heldRows"] == 0
    assert report["decisions"][0]["publicationMode"] == "explicit_unavailable_retirement"
    assert report["decisions"][0]["retired"] is True


def test_hapitas_unfingerprinted_unavailable_evidence_never_retires():
    url = "https://hapitas.jp/item/detail/itemid/101355"
    sources = {"hapitas": {"id": "hapitas", "search_domains": ["hapitas.jp"]}}
    policy = {"enabled": True, "sources": ["hapitas"]}
    row = {
        "offerKey": f"キングショット|hapitas|Android|{url}",
        "game": "キングショット", "site": "hapitas", "provider": "",
        "url": url, "sourceUrl": url, "reward": "16320",
        "type": "StepUp", "condition": "既存条件", "deadline": "既存期限",
        "platform": "Android", "verified": "true", "updatedAt": "2026-09-01",
    }
    item = {
        "source": "hapitas", "game": "キングショット", "url": url,
        "checkedAt": NOW,
        "sourceEvidence": {
            "state": "unavailable", "reason": "source_offer_unavailable",
            "parserVersion": "hapitas-detail-review-v2",
            "offerId": "101355", "name": "キングショット",
            "unavailableMarker": "この広告は終了しています",
            "evidenceFingerprint": "wrong",
        },
    }
    updated, report = publication.prepare([row], [item], sources, NOW, policy)
    assert updated == [row]
    assert report["retiredRows"] == 0
    assert report["heldRows"] == 1


def test_unavailable_offer_preserves_previous_value(warau_markup):
    row, item = sample(warau_markup.replace("テストゲーム（StepUp）</title>", "掲載終了のご案内</title>"))
    result, report = publication.prepare([row], [item], SOURCES, NOW, POLICY, True)
    assert result == [row] and report["heldRows"] == 1


def test_daily_entrypoint_writes_valid_snapshot_once(tmp_path, monkeypatch, warau_markup):
    import csv
    import daily_scan_review as daily
    from tests.test_daily_scan_review import setup_refresh
    module, _ = setup_refresh(tmp_path, monkeypatch, count=0)
    monkeypatch.setattr(daily, "direct", module)
    monkeypatch.setattr(daily, "ROOT", tmp_path)
    module.POLICY.write_text(json.dumps({"comparisonSources": ["warau"],
        "games": {"テストゲーム": {"enabled": True}}, "structuredPublication": POLICY}))
    module.TARGETS.write_text(json.dumps({"games": [{"game": "テストゲーム", "aliases": ["テストゲーム"]}]}))
    module.SOURCES.write_text(json.dumps({"sources": list(SOURCES.values())}))
    row, _ = sample(warau_markup)
    with module.PUBLISHED.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=module.FIELDS)
        writer.writeheader(); writer.writerow(row)
    calls = []
    def fetch(url, source):
        calls.append(url)
        return ("原則として1ポイント＝1円" if "/help/" in url else warau_markup), url
    monkeypatch.setattr(module, "fetch_first_party", fetch)
    assert daily.main() == 0
    with module.PUBLISHED.open() as f:
        updated = list(csv.DictReader(f))[0]
    assert updated["reward"] == "300"
    assert "20日以内にレベル10到達" in updated["condition"]
    assert calls.count(WARAU_URL) == 1 and len(calls) == len(set(calls))
    report = json.loads((tmp_path / "data/daily_scan_review.json").read_text())
    assert report["existingPublication"]["updatedRows"] == 1
    assert report["publishedGames"] == 0


def test_daily_hook_cannot_overwrite_concurrent_edit(tmp_path, monkeypatch):
    from tests.test_daily_scan_review import setup_refresh
    module, _ = setup_refresh(tmp_path, monkeypatch, count=1)
    concurrent = module.PUBLISHED.read_bytes() + b"\n"
    def edit(**kwargs):
        kwargs["rows"][0]["reward"] = "300"
        module.PUBLISHED.write_bytes(concurrent)
    assert module.main(after_scan=edit) == 2
    assert module.PUBLISHED.read_bytes() == concurrent
