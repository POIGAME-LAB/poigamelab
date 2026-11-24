"""Powl publication contract (operator decision 2026-11-24), checked on real pages captured that day."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct  # noqa: E402
import structured_publication as pub  # noqa: E402

FIX = ROOT / "tests/fixtures/daily_pages/powl"
META = json.loads((FIX / "index.json").read_text(encoding="utf-8"))
SOURCES = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
POLICY = json.loads((ROOT / "config/refresh_policy.json").read_text(encoding="utf-8"))["structuredPublication"]
NOW = "2026-11-24T16:30:00+00:00"
GAMES = {"powl_kingshot_ios_multi.html": "キングショット", "powl_mementomori_multi.html": "メメントモリ",
         "powl_tokyo_debunker_single.html": "東京ディバンカー", "powl_puzzles_survival_single.html": "パズル＆サバイバル",
         "powl_evertale_ambiguous_os.html": "エバーテイル"}


def _item(name):
    meta = META[name]
    raw = (FIX / name).read_text(encoding="utf-8")
    detail = direct.inspect_detail(meta["url"], SOURCES["powl"], [GAMES[name]],
                                   fetcher=lambda url, source: (raw, meta["finalUrl"]))
    return {"origin": "current_first_party_detail", "game": GAMES[name], "source": "powl",
            "requestedUrl": meta["url"], "url": detail["url"], "sourceEvidence": detail["sourceEvidence"],
            "checkedAt": NOW}


def _run(rows, items):
    return pub.prepare_verified(rows, items, SOURCES, NOW, POLICY, set(GAMES.values()), [], True)


def test_policy_publishes_powl():
    assert "powl" in POLICY["sources"] and "powl" in pub.REWARD_ONLY_CONTRACTS


@pytest.mark.parametrize("name, yen, kind", [
    ("powl_kingshot_ios_multi.html", "20300", "StepUp"),
    ("powl_mementomori_multi.html", "5000", "StepUp"),
    ("powl_tokyo_debunker_single.html", "200", "Single"),
    ("powl_puzzles_survival_single.html", "2800", "Single"),
])
def test_real_powl_pages_become_new_rows_with_exact_yen(name, yen, kind):
    out, report = _run([], [_item(name)])
    assert report["decisions"][0].get("holdReason") is None, report["decisions"]
    row = out[0]
    assert (row["site"], row["reward"], row["type"]) == ("powl", yen, kind)
    assert row["platform"] in {"iOS", "Android"} and row["updatedAt"] == "2026-11-25"
    assert "ポイント獲得条件" in row["condition"]


def test_mission_rewards_must_add_up_to_the_total():
    item = _item("powl_kingshot_ios_multi.html")
    e = item["sourceEvidence"]
    assert sum(pub.powl_step_points(e)) == e["displayedRewardPoints"] == 203000
    e["termsText"] = e["termsText"].replace("【400pt】", "【4,000pt】", 1)
    e["evidenceFingerprint"] = pub._fingerprint(e, pub.REWARD_ONLY_CONTRACTS["powl"]["fingerprintFields"])
    out, report = _run([], [item])
    assert out == [] and report["decisions"][0]["holdReason"] == "step_total_mismatch"


def test_page_without_os_and_tampered_evidence_still_hold():
    assert _item("powl_evertale_ambiguous_os.html")["sourceEvidence"]["state"] == "review_required"
    item = _item("powl_tokyo_debunker_single.html")
    item["sourceEvidence"]["verifiedCurrentRewardYen"] = 999
    out, report = _run([], [item])
    assert out == [] and "holdReason" in report["decisions"][0]


def test_existing_powl_row_refreshes_and_same_amount_only_moves_the_date():
    out, _ = _run([], [_item("powl_tokyo_debunker_single.html")])
    stale = copy.deepcopy(out)
    stale[0]["reward"], stale[0]["updatedAt"] = "150", "2026-11-01"
    again, report = _run(stale, [_item("powl_tokyo_debunker_single.html")])
    assert len(again) == 1 and again[0]["reward"] == "200" and report["rewardChanges"] == 1


@pytest.mark.parametrize("raw, key", [
    ("キングショット（iOS） マルチミッション", "キングショット"),
    ("メメントモリ（多段階）（iOS） - 課金総額5000円以上で成果", "メメントモリ"),
    ("【還元UP中】パズル＆サバイバル （コントロールセンターレベル17到達）（iOS）", "パズル&サバイバル"),
    ("キングショット2（iOS） マルチミッション", "キングショット2"),          # a different app never collapses
    ("iOS_クロンダイクの冒険/Klondike Adventures_30日以内に", None),       # unknown shape stays unmatched
])
def test_powl_titles_strip_only_decorations(raw, key):
    got = pub.catalog_title_key(pub.powl_title(raw))
    if key is None:
        assert got != pub.catalog_title_key("クロンダイクの冒険")
    else:
        assert got == pub.catalog_title_key(key)
