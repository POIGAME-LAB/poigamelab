"""Offline actual-parser -> strict gate -> daily CSV integration regressions."""
import copy
import csv
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import structured_publication as pub
import daily_scan_review as daily
from tests.test_structured_publication import sample, SOURCES, NOW
from tests.test_direct_offer_refresh_v1 import (
    warau_markup, coincome_markup, moppy_markup, WARAU_URL, COINCOME_URL,
    MOPPY_URL, _hapitas_fixture, _pointtown_fixture, _ecnavi_fixture,
    _amefuri_single_fixture, _amefuri_fixture,
)
from tests.test_daily_scan_review import setup_refresh
from tests.test_unified_daily_integration import _source, LISTING_URL, RATE_URL

POLICY = {"enabled": True, "sources": ["warau", "coincome", "moppy", "hapitas",
          "point_town", "ec_navi", "amefuri"], "verifiedExistingGameGate": True,
          "allowVerifiedExistingGameNewRows": True}


def envelope(item):
    return {**item, "origin": "current_first_party_detail", "requestedUrl": item["url"]}


def run(rows, items, sources=SOURCES, catalog=None, policy=None, rate=True, targets=None):
    return pub.prepare_verified(rows, items, sources, NOW, policy or POLICY,
                                {"テストゲーム"} if catalog is None else catalog,
                                targets or [], rate)


def test_changed_and_same_reward_refresh_date(warau_markup):
    row, item = sample(warau_markup)
    for reward in ("123", "300"):
        row["reward"] = reward
        out, report = run([row], [envelope(item)])
        assert out[0]["reward"] == "300"
        assert out[0]["updatedAt"] == "2026-09-16"
        assert report["rewardChanges"] == (reward != "300")
        assert report["updatedRows"] == 1
        assert row["updatedAt"] == "2026-09-01"


def test_strict_new_existing_game_offer_added_once_and_conditions_preserved(warau_markup):
    _, item = sample(warau_markup)
    out, report = run([], [envelope(item)] * 3)
    assert len(out) == report["addedRows"] == 1
    assert out[0]["reward"] == "300" and out[0]["platform"] == "iOS"
    assert "20日以内にレベル10到達" in out[0]["condition"]
    again, report = run(out, [envelope(item)])
    assert again == out and report["addedRows"] == report["updatedRows"] == 0


@pytest.mark.parametrize("failure", ["candidate", "veto", "comparison", "stale", "os",
    "identity", "url", "redirect", "rate", "fingerprint", "parser", "conflict", "duplicate",
    "other_game", "new_game", "alias_collision", "provider", "device", "deadline", "disabled_add", "nested_candidate"])
def test_bad_or_unproven_new_offer_never_added(warau_markup, failure):
    _, item = sample(warau_markup)
    item = envelope(item)
    sources, policy, catalog, rate, targets = copy.deepcopy(SOURCES), dict(POLICY), {"テストゲーム"}, True, []
    e = item["sourceEvidence"]
    if failure == "candidate": item["candidateOnly"] = True
    if failure == "nested_candidate": e["candidateOnly"] = True
    if failure == "veto": item["publicationAuthorized"] = False
    if failure == "comparison": item["origin"] = "comparison_listing"
    if failure == "stale": item["checkedAt"] = "2020-01-01"
    if failure == "os": e["platform"] = ""
    if failure == "identity": e["offerId"] = ""
    if failure == "url": item["url"] = "https://example.org/detail?id=101"
    if failure == "redirect": item["requestedUrl"] = WARAU_URL.replace("101", "999")
    if failure == "rate": rate = False
    if failure == "fingerprint": e["evidenceFingerprint"] = "tampered"
    if failure == "parser": e["parserVersion"] = "unreviewed-v99"
    if failure == "other_game": item["game"] = "テストゲーム2"; catalog.add("テストゲーム2")
    if failure == "new_game": catalog = set()
    if failure == "alias_collision":
        catalog.add("別ゲーム")
        targets = [{"game": "別ゲーム", "aliases": ["テストゲーム"]}]
    if failure == "provider": e["downstreamTermsRequired"] = True
    if failure == "device": sources["warau"]["acquisition_lane"] = "device"
    if failure == "deadline": e["termsText"] = "獲得条件 レベル10到達 獲得対象外 注意事項"
    if failure == "disabled_add": policy["allowVerifiedExistingGameNewRows"] = False
    items = [item]
    if failure in {"conflict", "duplicate"}:
        second = copy.deepcopy(item)
        second["sourceEvidence"]["state"] = "review_required"
        items.append(second)
    out, report = run([], items, sources, catalog, policy, rate, targets)
    assert out == [] and report["heldRows"] == 1, (failure, report)


@pytest.mark.parametrize("failure", ["os", "duplicate", "unverified", "provider", "conflict"])
def test_existing_identity_conflicts_hold_original(warau_markup, failure):
    row, item = sample(warau_markup)
    rows = [row]
    items = [envelope(item)]
    if failure == "os": row["platform"] = "Android"
    if failure == "duplicate": rows.append({**row, "offerKey": "second"})
    if failure == "unverified": row["verified"] = "false"
    if failure == "provider": row["provider"] = "SomeOfferwall"
    if failure == "conflict": items.append({**items[0], "sourceEvidence": {"state": "review_required"}})
    out, report = run(rows, items)
    assert out == rows and report["updatedRows"] == 0


def test_coincome_full_step_description_updates_and_creates_but_summary_cannot(coincome_markup):
    source = {"coincome": {"id": "coincome", "search_domains": ["cimcome.jp"]}}
    e = pub.direct.inspect_coincome_offer(coincome_markup, COINCOME_URL, COINCOME_URL, ["テストゲーム"])
    item = envelope({"game": "テストゲーム", "source": "coincome", "url": COINCOME_URL,
                     "checkedAt": NOW, "sourceEvidence": e})
    row = {"offerKey": "cc", "site": "coincome", "game": "テストゲーム", "platform": "Android",
           "url": COINCOME_URL, "verified": "true", "reward": "500", "condition": "旧条件"}
    out, report = run([row], [item], source)
    assert out[0]["reward"] == "600" and report["rewardChanges"] == 1
    out, report = run([], [item], source)
    assert len(out) == 1 and report["addedRows"] == 1
    assert "レベル20到達" in out[0]["condition"]
    item["sourceEvidence"].pop("publicationStepText")
    item["sourceEvidence"].pop("publicationStepFingerprint")
    out, report = run([], [item], source)
    assert not out and report["decisions"][0]["holdReason"] == "complete_step_conditions_required"


@pytest.mark.parametrize("sid", ["moppy", "hapitas", "point_town", "ec_navi", "amefuri"])
def test_reviewed_source_contract_promotes_fresh_detail_not_candidate_flag(sid, moppy_markup):
    if sid == "moppy":
        url, game = MOPPY_URL, "テストゲーム"
        raw = moppy_markup.replace("各成果地点は「POINT GET」をタップ後に遷移するページでご確認ください。",
                                   "レベル10に到達すると600Pを獲得できます。")
        raw = raw.replace("（StepUp）", "").replace("各成果地点クリア", "レベル10クリア")
        e = pub.direct.inspect_moppy_offer(raw, url, url, [game])
    elif sid == "hapitas":
        url, game = "https://hapitas.jp/item/detail/itemid/102497/", "Mistplay"
        e = pub.direct.inspect_hapitas_offer(_hapitas_fixture(), url, url, [game],
                                            reviewed_platform="iOS", publication_authorized=True)
    elif sid == "point_town":
        url, game = "https://www.pointtown.com/item/9265", "東京ディバンカー"
        e = pub.direct.inspect_pointtown_offer(_pointtown_fixture(), url, url, [game])
    elif sid == "ec_navi":
        url, game = "https://ecnavi.jp/ad/10721342/show/", "テストゲーム"
        raw = _ecnavi_fixture().replace("人気ソシャゲ〖NTE(Neverness to Everness)〗PC版無料登録", "テストゲーム（iOS）")
        raw = raw.replace("新規無料アカウント登録", "新規無料アカウント登録、30日以内にクリア")
        e = pub.direct.inspect_ecnavi_offer(raw, url, url, [game])
    else:
        url, game = "https://www.amefri.net/detail/id/140783", "弱虫ペダル レゾナンス・ぺダイズム"
        e = pub.direct.inspect_amefuri_offer(_amefuri_single_fixture(), url, url, [game])
    assert e["state"] == "parsed", e
    source = {sid: {"id": sid, "search_domains": [pub.direct.urlparse(url).hostname]}}
    item = envelope({"source": sid, "game": game, "url": url, "sourceEvidence": e, "checkedAt": NOW})
    row = {"offerKey": sid, "game": game, "site": sid, "url": url, "reward": "1",
           "platform": e["platform"], "verified": "true", "condition": "既存条件"}
    before = copy.deepcopy(item)
    out, report = run([row], [item], source, {game})
    assert report["rewardChanges"] == 1, report
    assert out[0]["reward"] != "1" and item == before
    item["candidateOnly"] = True
    assert run([row], [item], source, {game})[0] == [row]


@pytest.mark.parametrize("failure", ["missing_os", "missing_rate", "missing_id", "downstream"])
def test_moppy_no_shell_shortcut(moppy_markup, failure):
    url = MOPPY_URL
    raw = moppy_markup.replace("各成果地点は「POINT GET」をタップ後に遷移するページでご確認ください。", "レベル10到達で600P獲得できます。")
    e = pub.direct.inspect_moppy_offer(raw, url, url, ["テストゲーム"])
    field = {"missing_os": "platform", "missing_rate": "sourcePointRate", "missing_id": "offerId"}.get(failure)
    if field: e[field] = ""
    else: e["downstreamTermsRequired"] = True
    e["evidenceFingerprint"] = pub._fingerprint(e, pub.REWARD_ONLY_CONTRACTS["moppy"]["fingerprintFields"])
    item = envelope({"source": "moppy", "game": "テストゲーム", "url": url, "sourceEvidence": e, "checkedAt": NOW})
    source = {"moppy": {"id": "moppy", "search_domains": ["pc.moppy.jp"]}}
    assert run([], [item], source)[0] == []


@pytest.mark.parametrize("mode", ["change", "same", "add", "403", "timeout", "new_game", "candidate", "device"])
def test_daily_actual_parser_csv_roundtrip_no_duplicate_requests(tmp_path, monkeypatch, warau_markup, mode):
    module, _ = setup_refresh(tmp_path, monkeypatch, count=0)
    monkeypatch.setattr(daily, "direct", module)
    monkeypatch.setattr(daily, "ROOT", tmp_path)
    policy = {"comparisonSources": ["warau"], "unifiedDailySources": ["warau"],
              "games": {"テストゲーム": {"enabled": True}}, "structuredPublication": copy.deepcopy(POLICY)}
    if mode == "candidate": policy["structuredPublication"]["sources"] = ["coincome"]
    module.POLICY.write_text(json.dumps(policy))
    source = _source("warau")
    source["scheduled_known_detail_fetch_enabled"] = True
    if mode == "device": source["acquisition_lane"] = "device"
    module.SOURCES.write_text(json.dumps({"sources": [source]}))
    module.TARGETS.write_text(json.dumps({"games": [{"game": "テストゲーム", "known_urls_by_source": {"warau": [WARAU_URL]}}]}))
    (tmp_path / "games.csv").write_text("name\n" + ("別ゲーム" if mode == "new_game" else "テストゲーム") + "\n")
    row, _ = sample(warau_markup)
    if mode == "same": row["reward"] = "300"
    with module.PUBLISHED.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=module.FIELDS)
        writer.writeheader()
        if mode not in {"add", "new_game"}: writer.writerow(row)
    before = module.PUBLISHED.read_bytes()
    calls = []
    def fetch(url, source):
        calls.append(url)
        if url == LISTING_URL: return f'<a href="{WARAU_URL}">テストゲーム StepUp</a>', url
        if url == RATE_URL: return "ワラウでは原則として1ポイント＝1円です。", url
        assert url == WARAU_URL
        if mode == "403": raise HTTPError(url, 403, "Forbidden", {}, None)
        if mode == "timeout": raise TimeoutError()
        return warau_markup, url
    monkeypatch.setattr(module, "fetch_first_party", fetch)
    assert daily.main() == 0
    rows = module.read_published()
    status = json.loads(module.STATUS.read_text())
    health = status["sourceHealth"][0]
    assert len(calls) == len(set(calls))
    if mode in {"change", "same", "add"}:
        assert len(rows) == 1 and rows[0]["reward"] == "300"
        assert rows[0]["updatedAt"] == module.today_jst()
        assert health["parseSuccess"] == health["publicationEligible"] == 1
        assert status["publishedRewardChanges"] == (mode == "change")
    else:
        assert module.PUBLISHED.read_bytes() == before
        assert health["publicationEligible"] == 0
    if mode in {"403", "timeout"}: assert health["fetchFailed"] == 1 and health["parseSuccess"] == 0
    if mode == "candidate": assert health["parseSuccess"] == 1 and health["candidateOnly"] >= 1
    if mode == "device": assert calls == [] and health["deviceOnly"] is True


def test_policy_keeps_direct_no_new_rows_and_separate_device_lanes():
    policy = json.loads((ROOT / "config/refresh_policy.json").read_text())
    assert policy["publication"]["directRefreshNeverCreatesNewPublishedRows"] is True
    sources = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text())["sources"]}
    for sid in ("chobirich", "point_income"):
        assert sources[sid]["acquisition_lane"] == "device"
        assert not pub.direct.source_participates_in_new_game_ranking(sources[sid])


def test_amefuri_steps_and_paid_condition_are_atomic_with_yen():
    url, game = "https://www.amefri.net/detail/id/140198", "キングショット"
    e = pub.direct.inspect_amefuri_offer(_amefuri_fixture(), url, url, [game])
    source = {"amefuri": {"id": "amefuri", "search_domains": ["www.amefri.net"]}}
    item = envelope({"source": "amefuri", "game": game, "url": url, "checkedAt": NOW, "sourceEvidence": e})
    out, report = run([], [item], source, {game})
    assert report["addedRows"] == 1, report
    assert out[0]["reward"] == "4737"
    assert "35日以内に一括1600円以上3200円未満の課金" in out[0]["condition"]
    item["sourceEvidence"]["publicationStepText"] += " changed"
    assert run([], [item], source, {game})[0] == []


def test_hapitas_explicit_title_os_can_pass_without_stored_row_registry():
    url, game = "https://hapitas.jp/item/detail/itemid/102497/", "Mistplay"
    raw = _hapitas_fixture().replace("<h1>Mistplay</h1>", "<h1>Mistplay（iOS）</h1>")
    e = pub.direct.inspect_hapitas_offer(raw, url, url, [game])
    assert e["platformProvenance"] == "source_title" and e["publicationAuthorized"] is False
    item = envelope({"source": "hapitas", "game": game, "url": url, "checkedAt": NOW, "sourceEvidence": e})
    source = {"hapitas": {"id": "hapitas", "search_domains": ["hapitas.jp"]}}
    out, report = run([], [item], source, {game})
    assert report["addedRows"] == 1, report
    assert out[0]["reward"] == "9351" and "一括16000円以上の課金" in out[0]["condition"]


@pytest.mark.parametrize("defect", [None, "missing_decision", "tampered_reward", "tampered_os"])
def test_generated_new_row_must_match_gate_in_actual_pages_validator(tmp_path, warau_markup, defect):
    from validate_daily_publication import validate
    _, item = sample(warau_markup)
    rows, report = run([], [envelope(item)])
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    (tmp_path / "games.csv").write_text("name\nテストゲーム\n")
    (tmp_path / "config/point_sources.json").write_text(json.dumps({"sources": list(SOURCES.values())}))
    (tmp_path / "config/refresh_policy.json").write_text(json.dumps({"structuredPublication": POLICY}))
    before = tmp_path / "before.csv"
    before.write_text(",".join(pub.direct.FIELDS) + "\n")
    if defect == "tampered_reward": rows[0]["reward"] = "9999"
    if defect == "tampered_os": rows[0]["platform"] = "Android"
    with (tmp_path / "data/published_offers.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=pub.direct.FIELDS); writer.writeheader(); writer.writerows(rows)
    if defect != "missing_decision":
        (tmp_path / "data/daily_scan_review.json").write_text(json.dumps({"existingPublication": report}))
    artifact = tmp_path / "_site"; artifact.mkdir()
    (artifact / "data").mkdir(); (artifact / "config").mkdir()
    for name in ("games.csv", "data/published_offers.csv", "config/refresh_policy.json"):
        (artifact / name).write_bytes((tmp_path / name).read_bytes())
    for name in ("index.html", "offers.html", "game.html", "guides.html", "site-data.js"):
        (artifact / name).write_text("fixture")
    if defect:
        with pytest.raises(ValueError, match="new_offer_without_verified_gate_decision"):
            validate(tmp_path, before, artifact)
    else:
        assert validate(tmp_path, before, artifact)["publishedRows"] == 1
