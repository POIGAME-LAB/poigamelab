import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import structured_publication as publication
import unified_offer_snapshot as unified

EXPECTED = [
    "moppy", "warau", "coincome", "hapitas",
    "amefuri", "point_town", "ec_navi", "powl",
]
NOW = "2026-09-16T16:17:00+00:00"


def test_policy_declares_exact_unified_eight_sources():
    policy = json.loads((ROOT / "config/refresh_policy.json").read_text())
    assert policy["unifiedDailySources"] == EXPECTED
    source_cfg = json.loads((ROOT / "config/point_sources.json").read_text())
    sources = {row["id"]: row for row in source_cfg["sources"]}
    assert all(sources[sid].get("new_game_discovery_enabled") is True for sid in EXPECTED)


def test_unified_snapshot_keeps_one_site_games_and_groups_same_game():
    items = [
        {"source": "warau", "titleHint": "Puzzle Star（iOS）",
         "firstPartyCandidateUrl": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=10",
         "classification": "review"},
        {"source": "amefuri", "titleHint": "Puzzle Star (Android)",
         "firstPartyCandidateUrl": "https://www.amefri.net/detail/id/20",
         "classification": "review"},
        {"source": "powl", "titleHint": "Solo Kingdom",
         "firstPartyCandidateUrl": "https://web.powl.jp/reward/30",
         "classification": "review"},
    ]
    result = unified.build_snapshot(
        new_items=items, review_items=[], targets=[], source_ids=EXPECTED,
        checked_at=NOW, source_results=[]
    )
    assert result["groupCount"] == 2
    by_name = {g["game"]: g for g in result["groups"]}
    assert by_name["Puzzle Star"]["sourceCount"] == 2
    assert by_name["Puzzle Star"]["offerCount"] == 2
    assert by_name["Solo Kingdom"]["sourceCount"] == 1
    assert result["oneSiteGroupCount"] == 1


def _fingerprint(evidence, fields):
    payload = {field: evidence[field] for field in fields}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def contract_case(source):
    cases = {
        "hapitas": (
            "https://hapitas.jp/item/detail/itemid/123",
            {"offerId": "123", "name": "Game", "platform": "iOS",
             "platformProvenance": "reviewed_offer_registry",
             "displayedCurrentRewardPoints": 2200, "stepRewardPoints": [],
             "verifiedCurrentRewardPoints": 2200, "verifiedCurrentRewardYen": 2200,
             "rewardUnit": "Hapitas-pt", "sourcePointRate": "1pt=1JPY",
             "headerText": "Game 2200pt", "termsText": "ポイント対象条件 条件本文",
             "publicationAuthorized": False},
        ),
        "coincome": (
            "https://cimcome.jp/campaigns/details/123",
            {"offerId": "123", "name": "Game", "offerTitle": "iOS_Game", "platform": "iOS",
             "displayedRewardYen": 3300, "rewardUnit": "JPY-equivalent",
             "stepRewardYen": [], "stepTotalYen": None,
             "headerText": "iOS_Game 3300円",
             "termsText": "適用端末 キャッシュバック条件 承認条件 30日以内 否認条件"},
        ),
        "point_town": (
            "https://www.pointtown.com/item/123/",
            {"offerId": "123", "name": "Game", "platform": "iOS",
             "verifiedCurrentRewardPoints": 4400, "verifiedCurrentRewardYen": 4400,
             "rewardUnit": "PointTown-point", "sourcePointRate": "1pt=1JPY",
             "headerText": "Game で 4400 初回利用限定", "termsText": "ポイント獲得条件 条件本文",
             "publicationAuthorized": False},
        ),
        "ec_navi": (
            "https://ecnavi.jp/ad/123/show/",
            {"offerId": "123", "name": "Game", "platform": "iOS",
             "displayedPointCandidates": [55000], "verifiedCurrentRewardPoints": 55000,
             "verifiedCurrentRewardYen": 5500, "rewardUnit": "ECNavi-pt",
             "sourcePointRate": "10pt=1JPY", "headerText": "Game 55000pts (5500円分)",
             "termsText": "加算条件 加算条件詳細 加算時期", "publicationAuthorized": False},
        ),
        "amefuri": (
            "https://www.amefri.net/detail/id/123",
            {"offerId": "123", "name": "Game iOS", "platform": "iOS",
             "rewardMode": "StepUp",
             "displayedRewardYenCandidates": [6600], "displayedCurrentRewardYen": 6600,
             "stepRewardPoints": [30000, 36000], "stepTotalPoints": 66000,
             "verifiedCurrentRewardPoints": 66000, "verifiedCurrentRewardYen": 6600,
             "rewardUnit": "JPY-equivalent", "sourcePointRate": "10pt=1JPY",
             "headerText": "アメフリ経由で登録すると 6600円",
             "termsText": "ポイント獲得条件 ▼承認条件 30日以内 ▼却下条件",
             "publicationAuthorized": False},
        ),
    }
    return cases[source]


def test_reward_contracts_respect_publication_veto_and_preserve_prose():
    expected_safe = {"hapitas", "coincome", "point_town", "ec_navi", "amefuri"}
    assert expected_safe <= set(publication.REWARD_ONLY_CONTRACTS)
    assert "moppy" not in publication.REWARD_ONLY_CONTRACTS
    assert "powl" not in publication.REWARD_ONLY_CONTRACTS

    domains = {
        "hapitas": ["hapitas.jp", "www.hapitas.jp"],
        "coincome": ["cimcome.jp"],
        "point_town": ["www.pointtown.com", "pointtown.com"],
        "ec_navi": ["ecnavi.jp", "www.ecnavi.jp"],
        "amefuri": ["www.amefri.net", "amefri.net"],
    }
    for source in sorted(expected_safe):
        url, evidence = contract_case(source)
        contract = publication.REWARD_ONLY_CONTRACTS[source]
        evidence["state"] = "parsed"
        evidence["parserVersion"] = contract["parser"]
        evidence["evidenceFingerprint"] = _fingerprint(evidence, contract["fingerprintFields"])
        item = {"source": source, "game": "Game", "url": url,
                "checkedAt": NOW, "sourceEvidence": evidence}
        row = {"offerKey": source + "-1", "game": "Game", "site": source,
               "provider": "", "reward": "1", "condition": "KEEP CONDITION",
               "platform": "iOS", "type": "StepUp", "deadline": "KEEP DEADLINE",
               "updatedAt": "2026-09-01", "url": url, "sourceUrl": url, "verified": "true"}
        sources = {source: {"id": source, "search_domains": domains[source]}}
        updated, report = publication.prepare(
            [row], [item], sources, NOW,
            {"enabled": True, "sources": [source]}, False
        )
        if evidence.get("publicationAuthorized") is False:
            assert updated == [row], (source, report)
            assert report["updatedRows"] == report["rewardChanges"] == 0
            assert report["decisions"][0]["holdReason"] == "no_current_evidence"
        else:
            assert report["updatedRows"] == 1, (source, report)
            assert int(updated[0]["reward"]) > 1
        assert updated[0]["condition"] == "KEEP CONDITION"
        assert updated[0]["deadline"] == "KEEP DEADLINE"


def test_unified_snapshot_uses_verified_existing_detail_reward():
    url, evidence = contract_case("coincome")
    contract = publication.REWARD_ONLY_CONTRACTS["coincome"]
    evidence["state"] = "parsed"
    evidence["parserVersion"] = contract["parser"]
    evidence["evidenceFingerprint"] = _fingerprint(evidence, contract["fingerprintFields"])
    result = unified.build_snapshot(
        new_items=[],
        review_items=[{"game": "Township", "source": "coincome", "url": url,
                       "sourceEvidence": evidence}],
        targets=[{"game": "Township", "aliases": ["Township"]}],
        source_ids=EXPECTED, checked_at=NOW, source_results=[]
    )
    assert result["listedGroupCount"] == 1
    group = result["groups"][0]
    assert group["game"] == "Township"
    assert group["maxVerifiedRewardYen"] == 3300
    assert group["verifiedRewardCount"] == 1
