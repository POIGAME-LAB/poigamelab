import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import daily_scan_review as daily
from tests.test_daily_scan_review import setup_refresh
from tests.test_direct_offer_refresh_v1 import WARAU_URL, warau_markup

EIGHT = [
    "moppy", "warau", "coincome", "hapitas",
    "amefuri", "point_town", "ec_navi", "powl",
]
LISTING_URL = "https://www.warau.jp/contents/point/category/game"
RATE_URL = "https://www.warau.jp/help/qa/128/"
NOW_REWARD = "300"


def _source(source_id):
    domains = {
        "moppy": ["pc.moppy.jp"],
        "warau": ["www.warau.jp"],
        "coincome": ["cimcome.jp"],
        "hapitas": ["hapitas.jp"],
        "amefuri": ["www.amefri.net"],
        "point_town": ["www.pointtown.com"],
        "ec_navi": ["ecnavi.jp"],
        "powl": ["web.powl.jp"],
    }
    row = {
        "id": source_id,
        "search_domains": domains[source_id],
        "new_game_discovery_enabled": True,
        "scheduled_fetch_enabled": False,
        "direct_listing_urls": [],
        "direct_listing_limit": 0,
        "direct_detail_limit": 0,
    }
    if source_id == "warau":
        row.update({
            "direct_listing_urls": [LISTING_URL],
            "direct_listing_limit": 1,
            "direct_detail_limit": 2,
            "new_game_discovery_listing_limit": 1,
            "direct_detail_url_hints": ["pointEntrance.php"],
            "scheduled_known_detail_fetch_enabled": False,
        })
    return row


def test_one_warau_listing_scan_drives_discovery_and_listed_reward_update(
        tmp_path, monkeypatch, warau_markup):
    module, _ = setup_refresh(tmp_path, monkeypatch, count=0)
    monkeypatch.setattr(daily, "direct", module)
    monkeypatch.setattr(daily, "ROOT", tmp_path)

    module.POLICY.write_text(json.dumps({
        "comparisonSources": ["warau"],
        "unifiedDailySources": EIGHT,
        "minimumConfirmedSourcesForComparison": 1,
        "games": {"テストゲーム": {"enabled": True}},
        "structuredPublication": {
            "enabled": True,
            "sources": ["warau"],
            "preserveRowsOnHold": True,
        },
    }))
    module.TARGETS.write_text(json.dumps({"games": [{
        "game": "テストゲーム",
        "aliases": ["テストゲーム"],
    }]}))
    module.SOURCES.write_text(json.dumps({"sources": [_source(sid) for sid in EIGHT]}))

    with module.PUBLISHED.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=module.FIELDS)
        writer.writeheader()
        writer.writerow({
            "offerKey": "warau-test",
            "game": "テストゲーム",
            "site": "warau",
            "provider": "",
            "reward": "123",
            "condition": "以前の条件",
            "platform": "iOS",
            "type": "StepUp",
            "deadline": "以前の期限",
            "updatedAt": "2026-09-01",
            "url": WARAU_URL,
            "sourceUrl": WARAU_URL,
            "verified": "true",
        })

    listing_markup = (
        '<html><body><a href="' + WARAU_URL + '">テストゲーム StepUp</a></body></html>'
    )
    calls = []

    def fetch(url, source):
        calls.append(url)
        if url == LISTING_URL:
            return listing_markup, LISTING_URL
        if url == WARAU_URL:
            return warau_markup, WARAU_URL
        if url == RATE_URL:
            return "ワラウでは原則として1ポイント＝1円です。", RATE_URL
        raise AssertionError(f"unexpected fetch: {url}")

    monkeypatch.setattr(module, "fetch_first_party", fetch)
    assert daily.main() == 0

    print("DIAGNOSTIC_STATUS=" + module.STATUS.read_text())
    print("DIAGNOSTIC_DAILY=" + (tmp_path / "data/daily_scan_review.json").read_text())

    with module.PUBLISHED.open(newline="") as f:
        row = list(csv.DictReader(f))[0]
    assert row["reward"] == NOW_REWARD
    assert "10日以内にレベル5到達" in row["condition"]
    assert "20日以内にレベル10到達" in row["condition"]

    assert calls.count(LISTING_URL) == 1
    assert calls.count(WARAU_URL) == 1
    assert calls.count(RATE_URL) == 1
    assert len(calls) == len(set(calls))

    status = json.loads(module.STATUS.read_text())
    snapshot = status["listingSnapshot"]
    assert snapshot["uniqueListings"] == 1
    assert snapshot["reuseCount"] >= 1
    assert {"new_game_discovery", "existing_game_refresh"} <= set(snapshot["consumers"])
    assert status["unifiedDailySources"] == EIGHT
    assert status["publishedRewardChanges"] == 1

    report = json.loads((tmp_path / "data/daily_scan_review.json").read_text())
    assert report["existingPublication"]["updatedRows"] == 1
    assert report["existingPublication"]["rewardChanges"] == 1
    assert report["publishedGames"] == 0
