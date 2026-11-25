"""Real first-party pages captured on 2026-11-24 (capture-offer-pages workflow) that the daily
refresh could not read. Each test pins the fix for one hold reason seen in that day's log."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct  # noqa: E402
import structured_publication as pub  # noqa: E402

FIX = ROOT / "tests/fixtures/daily_pages"
META = json.loads((FIX / "index.json").read_text(encoding="utf-8"))
SOURCES = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
NOW = "2026-11-24T02:53:04+00:00"


def _inspect(name):
    meta = META[name]
    raw = (FIX / name).read_text(encoding="utf-8")
    detail = direct.inspect_detail(meta["url"], SOURCES[meta["source"]], [meta["game"]],
                                   fetcher=lambda url, source: (raw, meta["finalUrl"]))
    return meta, detail


def test_moppy_redirect_to_timeerror_is_an_ended_offer_not_a_parser_failure():
    _, detail = _inspect("moppy_ended_timeerror.html")
    assert detail["sourceEvidence"]["state"] == "unavailable"
    assert detail["sourceEvidence"]["reason"] == "source_offer_unavailable"


def test_warau_paused_offer_is_paused_not_ended_and_holds_the_row():
    meta, detail = _inspect("warau_paused.html")
    e = detail["sourceEvidence"]
    assert e["state"] == "unavailable" and e["reason"] == "source_offer_paused"
    row = {"offerKey": "k", "game": meta["game"], "site": "warau", "provider": "", "url": meta["url"], "sourceUrl": meta["url"],
           "reward": "22000", "platform": "iOS", "verified": "true", "condition": "c", "updatedAt": "2026-11-01"}
    item = {"origin": "current_first_party_detail", "game": meta["game"], "source": "warau", "requestedUrl": meta["url"],
            "url": meta["url"], "sourceEvidence": e, "checkedAt": NOW}
    policy = {"enabled": True, "verifiedExistingGameGate": True, "sources": ["warau"]}
    out, report = pub.prepare_verified([row], [item], SOURCES, NOW, policy, {meta["game"]}, [], True)
    assert out == [row] and report["decisions"][0]["holdReason"] == "source_offer_paused"
    assert report.get("retiredRows", 0) == 0


def test_moppy_unheaded_terms_with_explicit_achievement_deadline_parse():
    _, detail = _inspect("moppy_single_tokyo_debunker_unheaded.html")
    e = detail["sourceEvidence"]
    assert e["state"] == "parsed", e
    assert "獲得条件達成期限" in e["termsText"] and "広告概要" not in e["termsText"]


@pytest.mark.parametrize("name, days", [
    ("hapitas_tokyo_debunker.html", ["30日以内"]),
    ("hapitas_evertale_template.html", ["30日以内"]),
    ("hapitas_evertale_10days.html", ["10日以内"]),
    ("moppy_single_tokyo_debunker_unheaded.html", ["30日以内"]),
])
def test_achievement_deadline_is_read_after_boilerplate_and_ignores_launch_and_inquiry_windows(name, days):
    _, detail = _inspect(name)
    scope = pub.achievement_deadline(detail["sourceEvidence"])
    found = re.findall(r"\d+\s*(?:日|時間)以内", scope)
    assert found == days, found              # never the 1-hour launch rule or the 60/90-day inquiry window


def test_inquiry_window_alone_is_still_not_an_achievement_deadline():
    e = {"name": "x", "termsText": "【ポイント獲得条件】 レベル10到達で報酬獲得となります。 お問い合わせ受付期限はインストール日から60日以内です。"}
    with pytest.raises(pub.Hold):
        pub.achievement_deadline(e)
    e2 = {"name": "x", "termsText": "【ポイント獲得条件】 レベル10到達。 ※広告クリックから必ず1時間以内にアプリ初回起動をしてください※"}
    with pytest.raises(pub.Hold):
        pub.achievement_deadline(e2)


def test_hapitas_rows_with_stale_amounts_now_refresh_from_the_real_pages():
    rows = []
    items = []
    for name, old in (("hapitas_tokyo_debunker.html", "147"), ("hapitas_evertale_template.html", "182")):
        meta, detail = _inspect(name)
        e = detail["sourceEvidence"]
        rows.append({"offerKey": name, "game": meta["game"], "site": "hapitas", "provider": "", "url": meta["url"],
                     "sourceUrl": meta["url"], "reward": old, "platform": e["platform"], "verified": "true",
                     "condition": "旧条件", "updatedAt": "2026-09-28"})
        items.append({"origin": "current_first_party_detail", "game": meta["game"], "source": "hapitas",
                      "requestedUrl": meta["url"], "url": detail["url"], "sourceEvidence": e, "checkedAt": NOW})
    policy = {"enabled": True, "verifiedExistingGameGate": True, "sources": ["hapitas"]}
    out, report = pub.prepare_verified(rows, items, SOURCES, NOW, policy, {"東京ディバンカー", "エバーテイル"}, [], True)
    assert [d.get("holdReason") for d in report["decisions"]] == [None, None], report["decisions"]
    assert {r["game"]: r["reward"] for r in out} == {"東京ディバンカー": "189", "エバーテイル": "234"}
    assert all(r["updatedAt"] == "2026-11-24" for r in out)
