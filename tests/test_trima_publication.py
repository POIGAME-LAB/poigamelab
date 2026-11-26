"""Trima publication contract (operator decision 2026-11-26, real pages captured 2026-11-26).

The operator chose to publish the yen amount Trima prints on its own page, as printed
("交換手数料含む" included), without recalculating the exchange fee.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct  # noqa: E402
import structured_publication as pub  # noqa: E402

FIX = ROOT / "tests/fixtures/daily_pages/trima"
SOURCES = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
TARGETS = json.loads((ROOT / "config/game_targets.json").read_text(encoding="utf-8"))["games"]
POLICY = json.loads((ROOT / "config/refresh_policy.json").read_text(encoding="utf-8"))["structuredPublication"]
NOW = "2026-11-26T16:30:00+00:00"
PAGES = {
    "0bb06c4f": ("0bb06c4f-d519-4d9e-b01e-4117e1716645", "東京ディバンカー"),
    "f596a71c": ("f596a71c-85fd-43fe-b1e7-0db9c784651a", "パズル＆サバイバル"),
    "db10e473": ("db10e473-64dd-4dd3-b6ee-1306c4551eeb", "インポッシブルカート"),
    "d87bc6d2": ("d87bc6d2-6e4a-4e8a-807e-610404bd5fa3", "インポッシブルカート"),  # page is 「インポッシブルカート2」
}


def _aliases(game):
    target = next(t for t in TARGETS if t["game"] == game)
    return [game] + target.get("aliases", [])


def _item(key):
    offer_id, game = PAGES[key]
    url = f"https://web.trip-mile.com/ad/{offer_id}"
    raw = (FIX / f"{key}.html").read_text(encoding="utf-8")
    detail = direct.inspect_detail(url, SOURCES["trima"], _aliases(game), fetcher=lambda u, s: (raw, url))
    return {"origin": "current_first_party_detail", "game": game, "source": "trima", "requestedUrl": url,
            "url": detail["url"], "sourceEvidence": detail["sourceEvidence"], "checkedAt": NOW}


def _run(items, rows=()):
    return pub.prepare_verified(list(rows), items, SOURCES, NOW, POLICY, {t["game"] for t in TARGETS}, TARGETS, True)


def test_trima_is_a_publication_source():
    assert "trima" in POLICY["sources"] and "trima" in pub.REWARD_ONLY_CONTRACTS


def test_real_pages_publish_the_printed_yen_as_is():
    out, report = _run([_item("0bb06c4f"), _item("f596a71c")])
    holds = [d for d in report["decisions"] if d.get("holdReason")]
    assert holds == [], holds
    got = {(r["game"], r["reward"], r["platform"], r["type"]) for r in out}
    # 17,640 miles (147円相当), 400,000 miles (3,333円相当)
    assert got == {
        ("東京ディバンカー", "147", "不明", "Single"),
        ("パズル＆サバイバル", "3333", "不明", "Single"),
    }
    assert all(r["site"] == "trima" and r["verified"] == "true" for r in out)
    assert all("30日以内" in r["condition"] or "日以内" in r["condition"] for r in out)


def test_page_without_an_achievement_deadline_is_held():
    # The real インポッシブルカート page states no 達成期限, so it is not published.
    out, report = _run([_item("db10e473")])
    assert out == [] and report["decisions"][0]["holdReason"] == "achievement_deadline_not_explicit"


def test_sequel_title_is_not_published_as_the_catalog_game():
    out, report = _run([_item("d87bc6d2")])
    assert out == [] and report["decisions"][0]["holdReason"]


def test_printed_yen_must_match_the_evidence():
    item = _item("0bb06c4f")
    item["sourceEvidence"]["verifiedCurrentRewardYen"] += 1
    out, report = _run([item])
    assert out == [] and report["decisions"][0]["holdReason"]


def test_other_sources_still_need_an_os():
    contract = copy.deepcopy(pub.REWARD_ONLY_CONTRACTS["powl"])
    assert contract.get("platformNotStatedAsUnknown") is not True
    assert all(pub.REWARD_ONLY_CONTRACTS[s].get("platformNotStatedAsUnknown") is not True
               for s in pub.REWARD_ONLY_CONTRACTS if s != "trima")


def test_listing_finds_catalog_games():
    raw = (FIX / "listing_start24.json").read_text(encoding="utf-8")
    url = "https://web.trip-mile.com/api/ads/category?id=504&limit=24&start=24&sortBy=recommended"
    rows, _, _ = direct._trima_listing_rows(raw, expected_start=24)
    assert len(rows) == 24
    assert direct.discover_trima_target_listing_candidates(raw, url, SOURCES["trima"], ["存在しないゲーム名"]) == []


def test_daily_publication_validator_accepts_trima_unknown_platform_only(tmp_path):
    # 2026-11-26: the nightly refresh failed with new_offer_missing_platform_or_deadline because the
    # publication validator only knew iOS/Android. 不明 is allowed for sources whose pages never state an OS.
    import validate_daily_publication as val
    assert val.PLATFORM_NOT_STATED_SOURCES == {"trima"}
    assert val.new_row_platform_ok({"site": "trima", "platform": "不明"})
    assert not val.new_row_platform_ok({"site": "powl", "platform": "不明"})
    assert not val.new_row_platform_ok({"site": "trima", "platform": ""})
    assert val.new_row_platform_ok({"site": "moppy", "platform": "iOS"})
